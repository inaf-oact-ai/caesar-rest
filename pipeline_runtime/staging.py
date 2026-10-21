"""Stage multiple ordinary files/directories in one exclusive per-job workspace.

Offline helper only: caller guarantees immutable source snapshots, an exclusive
workspace, and appropriate container mounts. Does not submit any jobs.
"""
import json
import os
import shutil
import stat
import uuid
from pathlib import Path

from pipeline_runtime.integrity import verify_copy

class StagingError(Exception):
	"""Invalid staging request or incomplete preparation."""


def _inside(path, parent):
	return path == parent or parent in path.parents


def _check_source(source):
	p = Path(source)
	if not p.is_absolute() or p.is_symlink() or not p.exists():
		raise StagingError('Source must be an existing absolute non-symlink file or directory')
	mode = p.lstat().st_mode
	if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
		raise StagingError('Source must be a regular file or directory')
	if p.is_dir():
		for root, dirs, files in os.walk(str(p), followlinks=False):
			for name in dirs + files:
				child = Path(root) / name
				child_mode = child.lstat().st_mode
				if not (stat.S_ISDIR(child_mode) or stat.S_ISREG(child_mode)):
					raise StagingError('Source contains symlink or special file: %s' % child)
	return p.resolve(strict=True)


def _check_reference_source(source):
	"""Validate a canonical read-only source without copying it.

	Reject symlinks, including symlinked path components.
	The caller must separately authorize the dataset location.
	"""

	p = Path(source)

	if not p.is_absolute() or not p.is_dir():
		raise StagingError(
			'Reference source must be an existing absolute directory'
		)

	if str(p.resolve(strict=True)) != str(p):
		raise StagingError(
			'Reference source must be canonical'
		)

	# Reject symlinks anywhere within the source directory.
	# Do not follow links during inspection.
	for root, dirs, files in os.walk(str(p), followlinks=False):
		for name in dirs + files:
			child = Path(root) / name
			mode = child.lstat().st_mode

			if not (
				stat.S_ISDIR(mode)
				or stat.S_ISREG(mode)
			):
				raise StagingError(
					'Reference source contains symlink or special file: %s' %
					child
				)

	return p


def _validate_name(name):
	if not isinstance(name, str) or name in ('', '.', '..', 'staging.json'):
		raise StagingError('Invalid destination name')
	if '/' in name or '\\' in name or '\x00' in name or name.startswith('.staging-'):
		raise StagingError('Invalid destination name')
	return name


def _set_writable(destination, writable):
	paths = [destination]
	if destination.is_dir():
		for root, dirs, files in os.walk(str(destination), followlinks=False):
			paths.extend(Path(root) / name for name in dirs + files)
	for path in paths:
		perms = stat.S_IMODE(path.stat().st_mode)
		path.chmod((perms | stat.S_IWUSR) if writable else (perms & ~0o222))


def _measured_size(path):
	"""Count bytes in regular files, rejecting links/special files."""
	if path.is_symlink():
		raise StagingError('Symlink in v2 input')

	mode = path.lstat().st_mode

	if stat.S_ISREG(mode):
		return path.stat().st_size

	if not stat.S_ISDIR(mode):
		raise StagingError('Special file in v2 input')

	total = 0

	for root, dirs, files in os.walk(str(path), followlinks=False):
		for name in dirs + files:
			child = Path(root) / name
			kind = child.lstat().st_mode

			if stat.S_ISREG(kind):
				total += child.stat().st_size
			elif not stat.S_ISDIR(kind):
				raise StagingError('Symlink or special file in v2 input')

	return total


def stage_inputs(inputs, workspace):
	"""Stage a nonempty list of {'source', 'name', 'mode', 'writable'} inputs.

	All validation precedes copying. The input directory is claimed exclusively;
	one consolidated READY manifest is published *only* after every copy passes
	checks. On any failure partial input data remains for investigation, but no
	READY manifest is published. Sources must remain stable during the operation.
	"""
	base = Path(workspace)
	if not base.is_absolute() or base.is_symlink() or not base.is_dir():
		raise StagingError('Workspace must be an existing absolute non-symlink directory')
	
	base = base.resolve(strict=True)
	if not isinstance(inputs, (list, tuple)) or not inputs:
		raise StagingError('inputs must be a nonempty list')
	
	prepared = []
	names = set()
	for spec in inputs:
		if not isinstance(spec, dict):
			raise StagingError('Each input must be an object')
			
		mode = spec.get('mode', 'copy')
		if mode not in ('copy', 'reference_ro'):
			raise StagingError(
				'Unsupported staging mode: %s' % mode
			)

		if mode == 'reference_ro':
			if spec.get('writable') is not False:
				raise StagingError(
					'Read-only references require writable=False'
				)
				
		writable = spec.get('writable', True)
		if not isinstance(writable, bool):
			raise StagingError('writable must be boolean')
		
		if mode == 'reference_ro':
			src = _check_reference_source(spec.get('source'))
		else:
			src = _check_source(spec.get('source'))
				
		if _inside(base, src) or _inside(src, base):
			raise StagingError('Source and workspace must not overlap')
			
		name = _validate_name(spec.get('name', src.name))
		if name in names:
			raise StagingError('Duplicate destination name: %s' % name)

		names.add(name)

		if 'kind' in spec or 'size_bytes' in spec:
			kind = spec.get('kind')
			size = spec.get('size_bytes')

			if kind not in ('file', 'directory') or type(size) is not int or size < 0:
				raise StagingError('Invalid v2 input metadata')

			if kind != ('directory' if src.is_dir() else 'file'):
				raise StagingError('v2 source kind mismatch')

			if _measured_size(src) != size:
				raise StagingError('v2 source size mismatch')

		prepared.append((src, name, writable, mode))


	input_dir = base / 'input'
	try:
		input_dir.mkdir(mode=0o700)
	except FileExistsError:
		raise StagingError('Workspace input directory already exists; refusing overwrite')

	entries = []
	try:
			
		for src, name, writable, mode in prepared:
			dest = input_dir / name

			if mode == 'reference_ro':
				# A placeholder is created inside the private
				# workspace, but no dataset bytes are copied.
				#
				# EXECUTE will eventually mount the authorized
				# source over this placeholder as read-only.
				# No symbolic link to the source is created.
				dest.mkdir(mode=0o700)

				source_stat = src.stat()

				entries.append({
					'name': name,
					'source': str(src),
					'private_path': str(dest),
					'input_type': 'directory',
					'strategy': 'read_only_reference',
					'input_isolation': 'shared_read_only',
					'writable': False,
					'source_dev': source_stat.st_dev,
					'source_ino': source_stat.st_ino
				})

				continue

			
			if src.is_dir():
				shutil.copytree(str(src), str(dest), symlinks=True)
			else:
				shutil.copy2(str(src), str(dest), follow_symlinks=False)
			
			_check_source(dest)

			# For v2, verify the private copy before publishing READY.
			original = next(
				item for item in inputs
				if item.get('name', Path(item['source']).name) == name
			)

			if 'kind' in original or 'size_bytes' in original:
				if ('directory' if dest.is_dir() else 'file') != original['kind']:
					raise StagingError('v2 staged kind mismatch')

				if _measured_size(dest) != original['size_bytes']:
					raise StagingError('v2 staged size mismatch')

				try:
					verify_copy(dest, original)
				except ValueError as exc:
					raise StagingError('v2 staged digest mismatch') from exc

			_set_writable(dest, writable)
			
			entries.append({
				'name': name, 'source': str(src), 'private_path': str(dest),
				'input_type': 'directory' if dest.is_dir() else 'file',
				'strategy': 'full_copy', 'input_isolation': 'private_copy',
				'writable': writable
			})
		manifest = {'staging_state': 'READY', 'inputs': entries}
		tmp = input_dir / ('.staging-' + uuid.uuid4().hex)
		with open(str(tmp), 'x') as fp:
			json.dump(manifest, fp, indent=2, sort_keys=True)
			fp.flush()
			os.fsync(fp.fileno())
		os.replace(str(tmp), str(input_dir / 'staging.json'))
		return manifest
	except Exception as exc:
		raise StagingError('Staging failed; partial input retained without READY manifest: %s' % exc)


def stage_input(source, workspace, mode='copy', writable=True, name=None):
	"""Backward-compatible single-input staging API and manifest fields."""
	result = stage_inputs([{
		'source': source, 'name': name if name is not None else Path(source).name,
		'mode': mode, 'writable': writable
	}], workspace)
	entry = dict(result['inputs'][0])
	entry['staging_state'] = result['staging_state']
	return entry
