"""Generic, offline file/directory staging into a private per-job workspace.

Not connected to HTTP submission or Slurm. The caller must guarantee an
exclusive workspace and stable source, and enforce container mounts separately.
Only full-copy staging is implemented; no hardlinks or implicit symlink follows.
"""
import json
import os
import shutil
import stat
import uuid
from pathlib import Path


class StagingError(Exception):
	"""Unsafe input or incomplete staging."""


def _absolute_existing_directory(value, label):
	p = Path(value)
	if not p.is_absolute() or p.is_symlink() or not p.is_dir():
		raise StagingError('%s must be an existing absolute non-symlink directory' % label)
	return p.resolve(strict=True)


def _check_source(source):
	p = Path(source)
	if not p.is_absolute() or p.is_symlink() or not p.exists():
		raise StagingError('Source must be an existing absolute non-symlink file or directory')
	mode = p.lstat().st_mode
	if stat.S_ISREG(mode):
		return p.resolve(strict=True)
	if not stat.S_ISDIR(mode):
		raise StagingError('Source must be a regular file or directory')
	for root, dirs, files in os.walk(str(p), followlinks=False):
		for name in dirs + files:
			child = Path(root) / name
			child_mode = child.lstat().st_mode
			if not (stat.S_ISDIR(child_mode) or stat.S_ISREG(child_mode)):
				raise StagingError('Source contains symlink or special file: %s' % child)
	return p.resolve(strict=True)


def _inside(path, parent):
	return path == parent or parent in path.parents


def stage_input(source, workspace, mode='copy', writable=True, name=None):
	"""Copy one file/directory to workspace/input and publish a READY manifest.

	Refuses to reuse an existing input/ directory. A failed copy leaves input/
	for diagnosis but never writes READY. Requires stable sources and an exclusive
	workspace supplied by a trusted caller. `writable` controls destination
	permissions for supported ordinary file modes, not mount-level access.
	"""
	if mode != 'copy':
		raise StagingError('Unsupported staging mode: %s' % mode)
	if not isinstance(writable, bool):
		raise StagingError('writable must be boolean')
	src = _check_source(source)
	base = _absolute_existing_directory(workspace, 'Workspace')
	if _inside(base, src) or _inside(src, base):
		raise StagingError('Source and workspace must not overlap')
	filename = name if name is not None else src.name
	if not isinstance(filename, str) or filename in ('', '.', '..') or '/' in filename or '\\' in filename:
		raise StagingError('Invalid destination name')
	input_dir = base / 'input'
	if input_dir.exists() or input_dir.is_symlink():
		raise StagingError('Workspace input directory already exists; refusing overwrite')
	# Exclusive reservation: concurrent attempts cannot both claim the same input/.
	try:
		input_dir.mkdir(mode=0o700)
	except FileExistsError:
		raise StagingError('Workspace input directory already claimed')
	destination = input_dir / filename
	try:
		if src.is_dir():
			shutil.copytree(str(src), str(destination), symlinks=True)
		else:
			shutil.copy2(str(src), str(destination), follow_symlinks=False)
		# Verify the copy contains no symlink or special file, including a source
		# changed between preflight inspection and the copy operation.
		_check_source(destination)
		if writable:
			# chmod only the private copy; no chmod of source is performed.
			for root, dirs, files in os.walk(str(destination)) if destination.is_dir() else []:
				for item in dirs + files:
					p = Path(root) / item
					p.chmod(p.stat().st_mode | stat.S_IWUSR)
			destination.chmod(destination.stat().st_mode | stat.S_IWUSR)
		else:
			for root, dirs, files in os.walk(str(destination)) if destination.is_dir() else []:
				for item in dirs + files:
					p = Path(root) / item
					p.chmod(p.stat().st_mode & ~0o222)
			destination.chmod(destination.stat().st_mode & ~0o222)
		if destination.is_file():
			perms = destination.stat().st_mode
			destination.chmod((perms | stat.S_IWUSR) if writable else (perms & ~0o222))
		manifest = {
			'staging_state': 'READY', 'strategy': 'full_copy',
			'source': str(src), 'private_path': str(destination),
			'input_isolation': 'private_copy', 'writable': writable,
			'input_type': 'directory' if destination.is_dir() else 'file'
		}
		temporary = input_dir / ('.staging-' + uuid.uuid4().hex)
		with open(str(temporary), 'x') as fp:
			json.dump(manifest, fp, indent=2, sort_keys=True)
			fp.flush()
			os.fsync(fp.fileno())
		os.replace(str(temporary), str(input_dir / 'staging.json'))
		return manifest
	except Exception as exc:
		raise StagingError('Staging failed; input directory retained for inspection: %s' % exc)
