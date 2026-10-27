"""Pure mapping of trusted Slurm-host staged paths to Singularity paths.

No filesystem access and no job submission. The caller supplies trusted mount
configuration and must separately validate ownership, symlinks and READY data.
"""
import posixpath


class ContainerPathError(ValueError):
	"""Missing, ambiguous, or unsafe bind-mount mapping."""


def _path(value, label):
	if not isinstance(value, str) or not value.startswith('/') or '\x00' in value or '\n' in value:
		raise ContainerPathError('%s must be a clean absolute POSIX path' % label)
	if any(part in ('.', '..') for part in value.split('/')):
		raise ContainerPathError('%s contains dot path components' % label)
	if '//' in value or (value != '/' and value.endswith('/')):
		raise ContainerPathError('%s is not normalized' % label)
	if posixpath.normpath(value) != value:
		raise ContainerPathError('%s is not normalized' % label)
	return value


def _within(path, root):
	return path == root or path.startswith(root.rstrip('/') + '/')


def _mounts(binds):
	if not isinstance(binds, (list, tuple)) or not binds:
		raise ContainerPathError('At least one bind mount is required')
	result = []
	sources = set()
	for bind in binds:
		if not isinstance(bind, dict):
			raise ContainerPathError('Each bind must be a mapping')
		src = _path(bind.get('source'), 'Mount source')
		dst = _path(bind.get('destination'), 'Mount destination')
		if src in sources:
			raise ContainerPathError('Duplicate bind source: %s' % src)
		sources.add(src)
		result.append((src, dst))
	return result


def _join_mapped(destination, path, source):
	rel = posixpath.relpath(path, source)
	return destination if rel == '.' else posixpath.join(destination, rel)


def map_host_path(host_path, workspace, binds):
	"""Map a private host path within workspace using longest source-prefix match.

	All inputs are trusted paths, not values from REST clients or manifest JSON.
	Only lexical POSIX mapping is performed: symlink/ownership validation and
	Singularity's effective overlapping-bind behavior remain caller duties.
	"""
	path = _path(host_path, 'Host path')
	base = _path(workspace, 'Workspace')
	if not _within(path, base):
		raise ContainerPathError('Path is outside private workspace')
	mounts = _mounts(binds)
	candidates = [(src, dst) for src, dst in mounts if _within(path, src)]
	if not candidates:
		raise ContainerPathError('No bind mount covers host path')
	src, dst = max(candidates, key=lambda item: len(item[0]))
	# Do not accept nested source mounts that could redirect private data
	# outside the workspace's container-visible subtree.
	workspace_candidates = [(s, d) for s, d in mounts if _within(base, s)]
	if not workspace_candidates:
		raise ContainerPathError('No bind mount covers private workspace')
	ws_src, ws_dst = max(workspace_candidates, key=lambda item: len(item[0]))
	ws_container = _join_mapped(ws_dst, base, ws_src)
	mapped = _join_mapped(dst, path, src)
	if not _within(mapped, ws_container):
		raise ContainerPathError('Mapped path escapes container workspace')
	return mapped


def map_staged_inputs(staged_paths, workspace, binds):
	"""Map an already validated {name: private_host_path} resolver result."""
	if not isinstance(staged_paths, dict) or not staged_paths:
		raise ContainerPathError('staged_paths must be a nonempty mapping')
	return {name: map_host_path(path, workspace, binds) for name, path in staged_paths.items()}
