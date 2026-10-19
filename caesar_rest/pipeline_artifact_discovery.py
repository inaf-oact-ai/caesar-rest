"""Discover completed pipeline output files from an application output contract.

No database writes or job-state transitions occur in this module. Call only
with a trusted job workspace and server-owned application output contract.
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


def discover_artifacts(workspace, contract, max_files=1000):
	"""Return deterministic metadata for files declared in ``job_outputs``.

	Only regular files within ``workspace/results`` are accepted. Symlinks in
	any component of the path are rejected, including the workspace itself.
	Glob patterns are restricted to a single results-directory level.
	Required exact paths must exist. Optional patterns may match nothing.
	"""
	if not isinstance(workspace, (str, os.PathLike)) or not os.path.isabs(workspace):
		raise ArtifactDiscoveryError('Workspace must be absolute')
	if not isinstance(contract, dict):
		raise ArtifactDiscoveryError('Output contract must be an object')
	if not isinstance(max_files, int) or isinstance(max_files, bool) or max_files < 1:
		raise ArtifactDiscoveryError('Invalid artifact limit')

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
			# lstat every component: never follow symlinks, including in subdirs.
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
			if not stat.S_ISREG(info.st_mode):
				raise ArtifactDiscoveryError('Artifact is not a regular file: %s' % relative)
			if relative in seen:
				raise ArtifactDiscoveryError('Duplicate artifact: %s' % relative)
			seen.add(relative)
			artifacts.append({
				'name': key,
				'relative_path': 'results/' + relative,
				'type': spec.get('type') or 'application/octet-stream',
				'role': spec.get('role') or 'output',
				'size_bytes': info.st_size,
			})
			if len(artifacts) > max_files:
				raise ArtifactDiscoveryError('Artifact count limit exceeded')
	return artifacts
