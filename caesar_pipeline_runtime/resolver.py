"""Resolve named staged inputs from a READY manifest, without trusting manifest paths.

This is an offline resolver. It does not submit or execute jobs. The caller
must enforce workspace ownership and arrange trusted container mounts.
"""
import json
import os
import stat
from pathlib import Path

from caesar_pipeline_runtime.staging import StagingError, _validate_name


def _safe_path(path, kind):
	if not path.is_absolute() or path.is_symlink():
		raise StagingError('%s must be an absolute non-symlink path' % kind)
	try:
		mode = path.lstat().st_mode
	except OSError as exc:
		raise StagingError('%s is missing: %s' % (kind, exc))
	if not stat.S_ISDIR(mode):
		raise StagingError('%s must be a directory' % kind)
	return path.resolve(strict=True)


def resolve_staged_inputs(workspace, required_names=None):
	"""Return {name: absolute_private_path} from a validated READY manifest.

	Rejects forged/traversing paths, symlinks, missing data, inconsistent metadata,
	duplicate names and incomplete staging. Never follows a manifest-supplied path
	to locate a file; it reconstructs expected paths from workspace and name.
	"""
	base = _safe_path(Path(workspace), 'Workspace')
	input_dir = _safe_path(base / 'input', 'Input directory')
	manifest_path = input_dir / 'staging.json'
	if manifest_path.is_symlink() or not manifest_path.is_file():
		raise StagingError('READY manifest is missing or is a symlink')
	try:
		with manifest_path.open('r', encoding='utf-8') as handle:
			manifest = json.load(handle)
	except (OSError, UnicodeError, ValueError) as exc:
		raise StagingError('Cannot read staging manifest: %s' % exc)
	if not isinstance(manifest, dict) or manifest.get('staging_state') != 'READY':
		raise StagingError('Staging manifest is not READY')
	entries = manifest.get('inputs')
	if not isinstance(entries, list) or not entries:
		raise StagingError('Manifest inputs must be a nonempty list')
	resolved = {}
	for entry in entries:
		if not isinstance(entry, dict):
			raise StagingError('Malformed staging entry')
		name = _validate_name(entry.get('name'))
		if name in resolved:
			raise StagingError('Duplicate staging name: %s' % name)
		private = input_dir / name
		if entry.get('private_path') != str(private):
			raise StagingError('Manifest private path mismatch: %s' % name)
		if entry.get('input_isolation') != 'private_copy' or entry.get('strategy') != 'full_copy':
			raise StagingError('Unsupported staging strategy: %s' % name)
		if not isinstance(entry.get('writable'), bool):
			raise StagingError('Invalid writable flag: %s' % name)
		kind = entry.get('input_type')
		if kind not in ('file', 'directory'):
			raise StagingError('Invalid input type: %s' % name)
		if private.is_symlink():
			raise StagingError('Staged input is symlink: %s' % name)
		try:
			mode = private.lstat().st_mode
		except OSError as exc:
			raise StagingError('Staged input is missing (%s): %s' % (name, exc))
		if kind == 'file' and not stat.S_ISREG(mode):
			raise StagingError('Expected regular staged file: %s' % name)
		if kind == 'directory' and not stat.S_ISDIR(mode):
			raise StagingError('Expected staged directory: %s' % name)
		if kind == 'directory':
			for root, dirs, files in os.walk(str(private), followlinks=False):
				for child in dirs + files:
					p = Path(root) / child
					m = p.lstat().st_mode
					if not (stat.S_ISDIR(m) or stat.S_ISREG(m)):
						raise StagingError('Staged directory contains symlink or special file: %s' % p)
		resolved[name] = str(private)
	if required_names is not None:
		if not isinstance(required_names, (list, tuple, set)) or not required_names:
			raise StagingError('required_names must be a nonempty sequence')
		for name in required_names:
			_validate_name(name)
			if name not in resolved:
				raise StagingError('Required staged input is missing: %s' % name)
	return resolved
