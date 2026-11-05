"""Application-independent, inclusion-only job archive construction.

Paths in archive_policy['include'] are workspace-relative POSIX globs.
Only wildcard basenames are accepted; no recursive globs or wildcard parents.
The archive never contains staged input payloads, symbolic links, or directories
of scientific data. The caller provides the application-specific policy.
"""

import glob
import io
import json
import os
import stat
import tarfile
import tempfile
from pathlib import Path


class ArchivePolicyError(ValueError):
	pass


DEFAULT_MAX_FILE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_FILES = 1000


def _validate_pattern(pattern):
	if not isinstance(pattern, str) or not pattern or '\\' in pattern or '\x00' in pattern:
		raise ArchivePolicyError('Invalid archive inclusion pattern')
	if pattern.startswith('/') or '**' in pattern:
		raise ArchivePolicyError('Archive patterns must be relative and nonrecursive')
	parts = pattern.split('/')
	if any(part in ('', '.', '..') for part in parts):
		raise ArchivePolicyError('Non-normalized archive inclusion pattern')
	if len(parts) < 2 or parts[0] != 'results':
		raise ArchivePolicyError('Archive inclusions must be under results/')
	if any(any(c in part for c in '*?[') for part in parts[:-1]):
		raise ArchivePolicyError('Wildcard archive directories are not supported')
	if any(part.startswith('.') for part in parts):
		raise ArchivePolicyError('Hidden archive paths are not supported')
	return pattern


def _safe_file(root, relative):
	path = root / relative
	current = root
	for part in relative.split('/'):
		current = current / part
		if current.is_symlink():
			raise ArchivePolicyError('Symlink in selected archive path: %s' % relative)
	try:
		mode = path.stat().st_mode
	except OSError as exc:
		raise ArchivePolicyError('Cannot stat selected archive path: %s' % relative) from exc
	if not stat.S_ISREG(mode):
		raise ArchivePolicyError('Selected archive entry is not a regular file: %s' % relative)
	return path


def make_diagnostic_archive(output_filename, source_dir, policy=None):
	"""Write an atomic, lightweight staged-job archive.

	Always archives the staging manifest if present. Application policy includes
	only explicitly matched files under results/. Per-file and total budgets
	prevent accidental multi-GB archives. Oversized files are recorded as omitted
	in archive_policy.json; they remain available via artifact retention.
	"""
	if policy is None:
		policy = {'include': []}
	if not isinstance(policy, dict) or not isinstance(policy.get('include'), list):
		raise ArchivePolicyError('Archive policy must declare an include list')

	patterns = [_validate_pattern(item) for item in policy['include']]
	max_file_bytes = policy.get('max_file_bytes', DEFAULT_MAX_FILE_BYTES)
	max_total_bytes = policy.get('max_total_bytes', DEFAULT_MAX_TOTAL_BYTES)
	max_files = policy.get('max_files', DEFAULT_MAX_FILES)
	for limit in (max_file_bytes, max_total_bytes, max_files):
		if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
			raise ArchivePolicyError('Invalid archive size/count limit')

	root = Path(os.path.abspath(source_dir))
	output_filename = os.path.abspath(output_filename)
	if not root.is_dir() or root.is_symlink():
		raise ArchivePolicyError('Invalid staged pipeline workspace')
	if os.path.commonpath((str(root), output_filename)) == str(root):
		raise ArchivePolicyError('Archive must be created outside its source workspace')

	selected = set()
	for pattern in patterns:
		for match in glob.glob(str(root / pattern)):
			relative = os.path.relpath(match, str(root)).replace(os.sep, '/')
			# Globs can only match a basename. Validate each real path anyway.
			if relative.startswith('../') or relative.startswith('/'):
				raise ArchivePolicyError('Archive inclusion escapes workspace')
			_safe_file(root, relative)
			selected.add(relative)

	staging = root / 'input' / 'staging.json'
	if staging.exists() or staging.is_symlink():
		_safe_file(root, 'input/staging.json')
		selected.add('input/staging.json')

	included = []
	omitted = []
	total_bytes = 0
	for relative in sorted(selected):
		path = _safe_file(root, relative)
		size = path.stat().st_size
		if size > max_file_bytes:
			omitted.append({'path': relative, 'reason': 'file_size_limit', 'size_bytes': size})
			continue
		if len(included) >= max_files or total_bytes + size > max_total_bytes:
			omitted.append({'path': relative, 'reason': 'archive_budget', 'size_bytes': size})
			continue
		included.append(relative)
		total_bytes += size

	root_name = root.name
	metadata = {
		'schema': 'caesar.pipeline-job-archive.v1',
		'profile': 'diagnostics',
		'complete_scientific_output': False,
		'included_files': included,
		'omitted_files': omitted,
	}
	payload = (json.dumps(metadata, indent=2, sort_keys=True) + '\n').encode('utf-8')

	fd, temporary_path = tempfile.mkstemp(
		prefix='.pipeline-archive-', suffix='.tmp',
		dir=os.path.dirname(output_filename)
	)
	try:
		with os.fdopen(fd, 'wb') as output:
			with tarfile.open(fileobj=output, mode='w:gz') as tar:
				for relative in included:
					path = _safe_file(root, relative)
					# Explicit file-only archive: no automatic directory traversal.
					tar.add(str(path), arcname=root_name + '/' + relative, recursive=False)
				info = tarfile.TarInfo(root_name + '/archive_policy.json')
				info.size = len(payload)
				info.mode = 0o644
				info.mtime = 0
				tar.addfile(info, io.BytesIO(payload))
		os.replace(temporary_path, output_filename)
	finally:
		if os.path.exists(temporary_path):
			os.unlink(temporary_path)
