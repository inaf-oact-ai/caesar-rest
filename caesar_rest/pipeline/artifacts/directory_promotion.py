"""Owner-scoped mixed file/directory retention, opt-in and serialized per run.

This module is activated only for runs declaring at least one directory.
Existing file-only retention records and behavior are untouched.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import stat
import tempfile

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import access
from caesar_rest.pipeline.artifacts import directory_retention as directory_copy
from caesar_rest.pipeline.artifacts import directory_integrity
from caesar_rest.pipeline.staging.workspace import workspace_for_job


def _source_directory(db, owner, run, artifact):
	"""Derive source ONLY from verified job record and registered relative path."""
	parts = access._safe_parts(artifact.get('relative_path'))
	job_id = run.get('job_id')
	job = db[owner + '.jobs'].find_one({
		'job_id': job_id, 'pipeline_id': run['pipeline_id'],
		'run_id': run['run_id'], 'execution_mode': 'staged_container',
		'app': run['application'], 'state': 'SUCCESS'
	})
	if job is None or str(job.get('exit_code')) != '0' or run.get('status') != 'COMPLETED':
		raise manager.PipelineError('Directory source job unavailable', 409)
	job_top_dir = job.get('job_top_dir')
	if not isinstance(job_top_dir, str) or not os.path.isabs(job_top_dir):
		raise manager.PipelineError('Invalid job workspace', 409)
	try:
		workspace = workspace_for_job(job_top_dir, job_id)
	except ValueError:
		raise manager.PipelineError('Invalid job workspace', 409)
	if run.get('artifact_workspace') != workspace:
		raise manager.PipelineError('Artifact workspace mismatch', 409)
	source = os.path.join(workspace, *parts)
	# copy_directory_artifact reopens all components with O_NOFOLLOW;
	# this preliminary check provides a controlled error for absent sources.
	if not os.path.isdir(source) or os.path.islink(source):
		raise manager.PipelineError('Directory source unavailable', 410)
	return source


def _write_sidecar(base, name, manifest):
	"""Write a compact, canonical manifest next to (not inside) scientific data."""
	payload = json.dumps(manifest, sort_keys=True, separators=(',', ':'),
		ensure_ascii=False).encode('utf-8')
	digest = hashlib.sha256(payload).hexdigest()
	fd, temp = tempfile.mkstemp(prefix='.pending-manifest-', dir=base)
	try:
		with os.fdopen(fd, 'wb') as output:
			output.write(payload)
			output.flush()
			os.fsync(output.fileno())
		os.replace(temp, os.path.join(base, name))
	finally:
		if os.path.exists(temp):
			os.unlink(temp)
	return digest


def _copy_file(db, owner, run, index, artifact, base, max_file_bytes):
	size = artifact.get('size_bytes')
	if type(size) is not int or size < 0 or size > max_file_bytes:
		raise manager.PipelineError('Artifact exceeds file retention limit', 413)
	source, _, _ = access.open_registered_artifact(db, owner, run, index)
	fd, temp = tempfile.mkstemp(prefix='.pending-file-', dir=base)
	digest = hashlib.sha256()
	count = 0
	try:
		with source, os.fdopen(fd, 'wb') as target:
			while True:
				block = source.read(1024 * 1024)
				if not block:
					break
				count += len(block)
				if count > size or count > max_file_bytes:
					raise manager.PipelineError('Artifact changed while copying', 409)
				target.write(block)
				digest.update(block)
			target.flush()
			os.fsync(target.fileno())
		if count != size:
			raise manager.PipelineError('Artifact changed while copying', 409)
		os.replace(temp, os.path.join(base, '%04d' % index))
	finally:
		if os.path.exists(temp):
			os.unlink(temp)
	return {'index': index, 'size_bytes': size, 'sha256': digest.hexdigest()}


def promote_mixed_run(db, owner, pipeline_id, node_id, run_id, root,
		max_file_bytes, max_directory_bytes, max_directory_entries,
		max_directory_depth):
	"""Serially publish all outputs; MongoDB is updated only on full success."""
	from caesar_rest.pipeline.artifacts import retention
	run = access.get_run(db, owner, pipeline_id, node_id, run_id)
	if run.get('status') != 'COMPLETED' or not run.get('artifacts_registered_at'):
		raise manager.PipelineError('Run artifacts are not registered', 409)
	artifacts = run.get('artifacts') or []
	if not artifacts or not any(a.get('kind') == 'directory' for a in artifacts):
		raise manager.PipelineError('Mixed retention requires directory artifacts', 409)
	if any(a.get('kind', 'file') not in ('file', 'directory') for a in artifacts):
		raise manager.PipelineError('Unsupported artifact kind', 409)
	base = retention.retained_directory(root, owner, pipeline_id, run_id)
	try:
		retention._mkdir_safe(base)
		# flock serializes all cooperating promoters of the same run on shared FS.
		lock_fd = os.open(os.path.join(base, '.retention.lock'),
			os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
		try:
			if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
				raise manager.PipelineError('Invalid retention lock', 409)
			fcntl.flock(lock_fd, fcntl.LOCK_EX)
			run = access.get_run(db, owner, pipeline_id, node_id, run_id)
			if run.get('retained_artifacts') is not None:
				return {'run_id': run_id, 'retained': True,
					'count': len(run['retained_artifacts']), 'already_retained': True}
			records = []
			for index, artifact in enumerate(artifacts):
				if artifact.get('kind', 'file') == 'file':
					records.append(_copy_file(db, owner, run, index, artifact, base, max_file_bytes))
					continue
				source = _source_directory(db, owner, run, artifact)
				target = os.path.join(base, '%04d' % index)
				if os.path.lexists(target):
					# Leftover unpublished result from a previous failed attempt:
					# refuse to overwrite rather than implicitly deleting it.
					raise manager.PipelineError('Uncommitted directory exists; administrative recovery required', 409)
				try:
					result = directory_copy.copy_directory_artifact(
						source, target, artifact,
						max_bytes=max_directory_bytes,
						max_entries=max_directory_entries,
						max_depth=max_directory_depth)
				except directory_copy.DirectoryRetentionError as exc:
					raise manager.PipelineError('Directory retention failed: %s' % exc, 409)
				manifest_name = '%04d.manifest.json' % index
				digest = _write_sidecar(base, manifest_name, result['manifest'])
				if digest != result['manifest_sha256']:
					raise manager.PipelineError('Directory manifest digest mismatch', 409)
				record = {
					'index': index, 'kind': 'directory', 'size_bytes': result['size_bytes'],
					'file_count': result['file_count'], 'directory_count': result['directory_count'],
					'manifest_name': manifest_name, 'manifest_sha256': digest
				}
				try:
					directory_integrity.verify_directory_artifact(
						base, index, record, max_entries=max_directory_entries,
						max_bytes=max_directory_bytes, max_depth=max_directory_depth)
				except directory_integrity.DirectoryIntegrityError as exc:
					raise manager.PipelineError('Retained directory verification failed: %s' % exc, 409)
				records.append(record)
			result = db.pipeline_runs.update_one({
				'owner': owner, 'pipeline_id': pipeline_id, 'node_id': node_id,
				'run_id': run_id, 'status': 'COMPLETED',
				'retained_artifacts': {'$exists': False}
			}, {'$set': {'retained_artifacts': records, 'retained_at': manager.utcnow()}})
			if result.modified_count != 1:
				raise manager.PipelineError('Artifact retention not recorded', 409)
			return {'run_id': run_id, 'retained': True,
				'count': len(records), 'already_retained': False}
		finally:
			os.close(lock_fd)
	except OSError as exc:
		raise manager.PipelineError('Artifact retention storage failure', 503) from exc
