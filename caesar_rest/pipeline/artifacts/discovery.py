"""Discover completed pipeline outputs from an application output contract.

This module performs metadata discovery only. Directory artifacts are not yet
supported by registration, retention, download, or downstream staging.
"""

import glob
import os
import stat
from pathlib import Path


class ArtifactDiscoveryError(ValueError):
	pass


def _safe_relative(value):
	if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
		raise ArtifactDiscoveryError('Invalid artifact path')
	if value.startswith('/') or any(part in ('', '.', '..') for part in value.split('/')):
		raise ArtifactDiscoveryError('Artifact path must be relative and normalized')
	return value


def _directory_summary(path, max_depth, max_entries, max_bytes):
	"""Inspect a directory tree without following symlinks.

	Depth is measured from the artifact root. Regular files and directories
	both count towards the entry limit. This is discovery, not a filesystem
	snapshot; copy-time validation remains necessary in a later milestone.
	"""
	files = 0
	directories = 0
	total = 0
	stack = [(path, 0)]
	while stack:
		current, depth = stack.pop()
		try:
			with os.scandir(str(current)) as entries:
				children = sorted(list(entries), key=lambda entry: entry.name)
		except OSError as exc:
			raise ArtifactDiscoveryError('Cannot inspect directory artifact') from exc
		for entry in children:
			if entry.is_symlink():
				raise ArtifactDiscoveryError('Symlink artifact rejected: %s' % entry.name)
			try:
				info = entry.stat(follow_symlinks=False)
			except OSError as exc:
				raise ArtifactDiscoveryError('Cannot inspect directory artifact') from exc
			if stat.S_ISDIR(info.st_mode):
				if depth + 1 > max_depth:
					raise ArtifactDiscoveryError('Artifact directory depth limit exceeded')
				directories += 1
				stack.append((Path(entry.path), depth + 1))
			elif stat.S_ISREG(info.st_mode):
				files += 1
				total += info.st_size
				if total > max_bytes:
					raise ArtifactDiscoveryError('Artifact directory size limit exceeded')
			else:
				raise ArtifactDiscoveryError('Special file in directory artifact')
			if files + directories > max_entries:
				raise ArtifactDiscoveryError('Artifact directory entry limit exceeded')
	return {'size_bytes': total, 'file_count': files, 'directory_count': directories}


def discover_artifacts(workspace, contract, max_files=1000, max_directory_entries=100000,
						max_directory_depth=16, max_directory_bytes=1024 * 1024 * 1024 * 1024):
	"""Discover declared files and directories under ``workspace/results``.

	``kind`` defaults to ``file`` for backwards compatibility. The directory
	limits are independent from the number of top-level registered artifacts.
	Only flat glob patterns are supported. A discovered directory never gets
	a checksum until later retention work.
	"""
	if not isinstance(workspace, (str, os.PathLike)) or not os.path.isabs(workspace):
		raise ArtifactDiscoveryError('Workspace must be absolute')
	if not isinstance(contract, dict):
		raise ArtifactDiscoveryError('Output contract must be an object')
	for value in (max_files, max_directory_entries, max_directory_depth, max_directory_bytes):
		if not isinstance(value, int) or isinstance(value, bool) or value < 1:
			raise ArtifactDiscoveryError('Invalid artifact discovery limit')

	root = Path(os.path.abspath(workspace))
	results = root / 'results'
	for part in (root, results):
		if part.is_symlink() or not part.is_dir():
			raise ArtifactDiscoveryError('Missing or unsafe workspace/results directory')

	artifacts = []
	seen = set()
	for key, spec in sorted(contract.items()):
		if not isinstance(key, str) or not key or not isinstance(spec, dict):
			raise ArtifactDiscoveryError('Invalid output contract entry')
		kind = spec.get('kind', 'file')
		if kind not in ('file', 'directory'):
			raise ArtifactDiscoveryError('Invalid artifact kind')
		exact = spec.get('path')
		pattern = spec.get('glob')
		if bool(exact) == bool(pattern):
			raise ArtifactDiscoveryError('Exactly one of path/glob must be declared')
		if exact:
			relatives = [_safe_relative(exact)]
		else:
			pattern = _safe_relative(pattern)
			if '/' in pattern or '**' in pattern:
				raise ArtifactDiscoveryError('Only flat glob patterns are supported')
			relatives = sorted(os.path.basename(x) for x in glob.glob(str(results / pattern)))
		if spec.get('required') and not relatives:
			raise ArtifactDiscoveryError('Missing required artifact: %s' % key)

		for relative in relatives:
			_safe_relative(relative)
			path = results / relative
			current = results
			for component in relative.split('/'):
				current = current / component
				if current.is_symlink():
					raise ArtifactDiscoveryError('Symlink artifact rejected: %s' % relative)
			try:
				info = path.stat()
			except FileNotFoundError:
				if exact and not spec.get('required'):
					continue
				raise ArtifactDiscoveryError('Missing required artifact: %s' % relative)
			if kind == 'file' and not stat.S_ISREG(info.st_mode):
				raise ArtifactDiscoveryError('Artifact is not a regular file: %s' % relative)
			if kind == 'directory' and not stat.S_ISDIR(info.st_mode):
				raise ArtifactDiscoveryError('Artifact is not a directory: %s' % relative)
			if relative in seen:
				raise ArtifactDiscoveryError('Duplicate artifact: %s' % relative)
			if len(artifacts) >= max_files:
				raise ArtifactDiscoveryError('Artifact count limit exceeded')
			seen.add(relative)
			item = {
				'name': key,
				'relative_path': 'results/' + relative,
				'type': spec.get('type') or 'application/octet-stream',
				'role': spec.get('role') or 'output',
				'size_bytes': info.st_size,
			}
			if kind == 'directory':
				item.update(_directory_summary(path, max_directory_depth,
					max_directory_entries, max_directory_bytes))
				item['kind'] = 'directory'
			artifacts.append(item)
	return artifacts
