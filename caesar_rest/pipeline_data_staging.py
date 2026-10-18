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
		if spec.get('mode', 'copy') != 'copy':
			raise StagingError('Only copy staging is supported')
		writable = spec.get('writable', True)
		if not isinstance(writable, bool):
			raise StagingError('writable must be boolean')
		src = _check_source(spec.get('source'))
		if _inside(base, src) or _inside(src, base):
			raise StagingError('Source and workspace must not overlap')
		name = _validate_name(spec.get('name', src.name))
		if name in names:
			raise StagingError('Duplicate destination name: %s' % name)
		names.add(name)
		prepared.append((src, name, writable))

	input_dir = base / 'input'
	try:
		input_dir.mkdir(mode=0o700)
	except FileExistsError:
		raise StagingError('Workspace input directory already exists; refusing overwrite')

	entries = []
	try:
		for src, name, writable in prepared:
			dest = input_dir / name
			if src.is_dir():
				shutil.copytree(str(src), str(dest), symlinks=True)
			else:
				shutil.copy2(str(src), str(dest), follow_symlinks=False)
			_check_source(dest)
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
