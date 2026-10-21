"""Resolve named staged inputs from a READY manifest, without trusting manifest paths.

This is an offline resolver. It does not submit or execute jobs. The caller
must enforce workspace ownership and arrange trusted container mounts.
"""
import json
import os
import stat
from pathlib import Path

from pipeline_runtime.staging import (
	StagingError,
	_validate_name,
	_check_reference_source,
)


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


def _trusted_reference_specs(base):
	"""Read the original server-generated staging input declarations."""

	spec_path = base / 'staging_spec.json'

	if spec_path.is_symlink() or not spec_path.is_file():
		raise StagingError('Trusted staging specification is missing')

	try:
		with spec_path.open('r', encoding='utf-8') as stream:
			spec = json.load(stream)
	except (OSError, ValueError) as exc:
		raise StagingError(
			'Cannot read trusted staging specification: %s' % exc
		)

	if not isinstance(spec, dict) or spec.get('version') != 1:
		raise StagingError(
			'Read-only references require a v1 staging specification'
		)

	items = spec.get('inputs')

	if not isinstance(items, list) or not items:
		raise StagingError('Invalid trusted staging inputs')

	references = {}

	for item in items:
		if not isinstance(item, dict):
			raise StagingError('Invalid trusted input descriptor')

		if item.get('mode') != 'reference_ro':
			continue

		if item.get('writable') is not False:
			raise StagingError('Trusted reference must be read-only')

		name = _validate_name(item.get('name'))

		if name in references:
			raise StagingError('Duplicate trusted reference name')

		source = item.get('source')

		if not isinstance(source, str):
			raise StagingError('Invalid trusted reference source')

		references[name] = source

	return references


def resolve_staged_inputs(
	workspace,
	required_names=None,
	include_references=False
):
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
		
	references = {}
	trusted_references = None	
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
		
		strategy = entry.get('strategy')

		if strategy == 'full_copy':
			if entry.get('input_isolation') != 'private_copy':
				raise StagingError('Invalid copied-input isolation')

		elif strategy == 'read_only_reference':
			if entry.get('input_isolation') != 'shared_read_only':
				raise StagingError('Invalid reference isolation')

			if entry.get('writable') is not False:
				raise StagingError('Reference must be read-only')

			if entry.get('input_type') != 'directory':
				raise StagingError('Reference must be a directory')

		else:
			raise StagingError(
				'Unsupported staging strategy: %s' % name
			)
		
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
						
	

		if strategy == 'read_only_reference':

			if trusted_references is None:
				trusted_references = _trusted_reference_specs(base)

			source = entry.get('source')

			if (
				not isinstance(source, str)
				or trusted_references.get(name) != source
			):
				raise StagingError(
					'Reference does not match trusted staging specification'
				)

			# A reference destination is only a mount point.
			# It must not contain user-created files.
			if any(private.iterdir()):
				raise StagingError(
					'Read-only reference mount point is not empty'
				)

			try:
				src = _check_reference_source(source)
				source_stat = src.stat()
			except (OSError, ValueError, TypeError) as exc:
				raise StagingError(
					'Reference source validation failed: %s' % exc
				)

			expected_dev = entry.get('source_dev')
			expected_ino = entry.get('source_ino')

			if (
				type(expected_dev) is not int
				or type(expected_ino) is not int
				or expected_dev != source_stat.st_dev
				or expected_ino != source_stat.st_ino
			):
				raise StagingError(
					'Reference source identity changed since PREPARE'
				)

			# Never permit a reference into the private workspace.
			if src == base or base in src.parents or src in base.parents:
				raise StagingError(
					'Reference source overlaps private workspace'
				)

			references[name] = {
				'source': str(src),
				'mount_point': str(private),
			}
		
			
		resolved[name] = str(private)
		
	if required_names is not None:
		if not isinstance(required_names, (list, tuple, set)) or not required_names:
			raise StagingError('required_names must be a nonempty sequence')
		for name in required_names:
			_validate_name(name)
			if name not in resolved:
				raise StagingError('Required staged input is missing: %s' % name)
				
	if include_references:
		return resolved, references

	return resolved	
	
	
