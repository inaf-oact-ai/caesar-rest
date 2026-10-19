"""Owner-scoped access to registered pipeline artifacts.

Only the trusted job record determines the workspace. Client paths are never
accepted. File opening rejects symbolic links in all path components.
"""

import os
import re
import stat

from caesar_rest import pipeline_manager as manager
from caesar_rest.pipeline_workspace import workspace_for_job


class ArtifactAccessError(manager.PipelineError):
	pass


def get_run(db, owner, pipeline_id, node_id, run_id):
	manager.validate_identifier(node_id, 'node_id')
	manager.get_pipeline(owner, pipeline_id)
	run = db.pipeline_runs.find_one({
		'owner': owner, 'pipeline_id': pipeline_id,
		'node_id': node_id, 'run_id': run_id
	})
	if run is None:
		raise ArtifactAccessError('Pipeline run not found', 404)
	return run


def public_artifacts(run):
	"""Return stable indices without leaking server paths."""
	items = run.get('artifacts') or []
	return [{'index': index, **{
		key: artifact[key] for key in ('name', 'relative_path', 'type', 'role', 'size_bytes')
		if key in artifact
	}} for index, artifact in enumerate(items)]


def _safe_parts(relative):
	if not isinstance(relative, str) or not relative.startswith('results/'):
		raise ArtifactAccessError('Invalid registered artifact path', 409)
	parts = relative.split('/')
	if len(parts) < 2 or any(not p or p in ('.', '..') or '\\' in p or '\x00' in p for p in parts):
		raise ArtifactAccessError('Invalid registered artifact path', 409)
	return parts


def open_registered_artifact(db, owner, run, index):
	"""Open only a registered regular file from the job's trusted workspace.

	Returns (binary_file, filename, media_type). Caller owns and closes file.
	"""
	items = run.get('artifacts') or []
	if not isinstance(index, int) or index < 0 or index >= len(items):
		raise ArtifactAccessError('Artifact not found', 404)
	artifact = items[index]
	parts = _safe_parts(artifact.get('relative_path'))
	job_id = run.get('job_id')
	job = db[owner + '.jobs'].find_one({
		'job_id': job_id, 'pipeline_id': run['pipeline_id'],
		'run_id': run['run_id'], 'execution_mode': 'staged_container',
		'app': run['application']
	})
	if job is None or run.get('status') != 'COMPLETED':
		raise ArtifactAccessError('Artifact is unavailable', 409)
	job_top_dir = job.get('job_top_dir')
	if not isinstance(job_top_dir, str) or not os.path.isabs(job_top_dir):
		raise ArtifactAccessError('Invalid registered workspace', 409)
	workspace = workspace_for_job(job_top_dir, job_id)
	if run.get('artifact_workspace') != workspace:
		raise ArtifactAccessError('Artifact workspace mismatch', 409)

	# Reject symlinks at each level before opening. Use dirfd + O_NOFOLLOW
	# to prevent a link swap from redirecting the final file open.
	components = [job_top_dir, workspace] + [os.path.join(workspace, *parts[:i]) for i in range(1, len(parts))]
	for path in components:
		if os.path.islink(path):
			raise ArtifactAccessError('Unsafe artifact path', 409)
	if not os.path.isdir(workspace):
		raise ArtifactAccessError('Artifact file no longer available', 410)

	flags_dir = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
	flags_file = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
	fds = []
	try:
		fds.append(os.open(workspace, flags_dir))
		for component in parts[:-1]:
			fds.append(os.open(component, flags_dir, dir_fd=fds[-1]))
		fd = os.open(parts[-1], flags_file, dir_fd=fds[-1])
		info = os.fstat(fd)
		if not stat.S_ISREG(info.st_mode):
			os.close(fd)
			raise ArtifactAccessError('Artifact is not a regular file', 409)
		if info.st_size != artifact.get('size_bytes'):
			os.close(fd)
			raise ArtifactAccessError('Artifact size changed after registration', 409)
		fileobj = os.fdopen(fd, 'rb')
	except FileNotFoundError:
		raise ArtifactAccessError('Artifact file no longer available', 410)
	except OSError as exc:
		raise ArtifactAccessError('Cannot safely open artifact', 409) from exc
	finally:
		for fd in reversed(fds):
			os.close(fd)
	return fileobj, parts[-1], artifact.get('type') or 'application/octet-stream'
