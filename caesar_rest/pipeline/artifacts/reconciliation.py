"""Explicit, append-only reconciliation of fully retained Pipeline V2 runs.

This administrative operation does not change scientific state, job archives,
existing artifact indices, or existing retained payloads. Only new regular-file
artifacts are supported in this first recovery milestone.
"""

import fcntl
import os
import stat

from caesar_rest.job_configurator import JobConfigurator
from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import access, directory_integrity, discovery
from caesar_rest.pipeline.artifacts import directory_promotion, directory_retention, resume, retention
from caesar_rest.pipeline.staging.workspace import workspace_for_job


class ArtifactReconciliationError(manager.PipelineError):
	def __init__(self, message, code=409):
		super().__init__(message, code)


def _check_existing(db, owner, run, base, root, max_directory_bytes,
		max_directory_entries, max_directory_depth):
	"""Verify published metadata and retained payloads without copying science data."""
	artifacts = run['artifacts']
	records = run['retained_artifacts']
	if not artifacts or len(artifacts) != len(records):
		raise ArtifactReconciliationError('Existing artifact retention is incomplete')
	paths = set()
	for index, (artifact, record) in enumerate(zip(artifacts, records)):
		path = artifact.get('relative_path')
		access._safe_parts(path)
		if path in paths or record.get('index') != index:
			raise ArtifactReconciliationError('Duplicate path or invalid retained index')
		paths.add(path)
		if artifact.get('kind') == 'directory':
			try:
				directory_integrity.verify_directory_manifest(
					base, index, record, max_bytes=max_directory_bytes,
					max_entries=max_directory_entries, max_depth=max_directory_depth)
			except directory_integrity.DirectoryIntegrityError as exc:
				raise ArtifactReconciliationError('Existing directory retention invalid: %s' % exc) from exc

		else:
			# Existing file is read and checksum-verified from retained
			# storage, not from the original job workspace.
			stream, _, _ = retention.open_retained_artifact(
				owner, run, index, root
			)
			with stream:
				pass

	return paths


def _load_verified_run(db, owner, pipeline_id, node_id, run_id):
	run = access.get_run(db, owner, pipeline_id, node_id, run_id)
	if (
		run.get('status') != 'COMPLETED'
		or run.get('job_state') != 'SUCCESS'
		or str(run.get('job_exit_code')) != '0'
		or not run.get('artifacts_registered_at')
		or not isinstance(run.get('artifacts'), list)
		or not isinstance(run.get('retained_artifacts'), list)
		or run.get('retention_status') not in (None, 'READY')
	):
		raise ArtifactReconciliationError('Run is not completed and fully retained')
	job = db[owner + '.jobs'].find_one({
		'job_id': run.get('job_id'), 'pipeline_id': pipeline_id,
		'run_id': run_id, 'execution_mode': 'staged_container',
		'app': run.get('application'), 'state': 'SUCCESS'
	})
	if job is None or str(job.get('exit_code')) != '0':
		raise ArtifactReconciliationError('Successful staged job record not found')
	job_top_dir = job.get('job_top_dir')
	if not isinstance(job_top_dir, str) or not os.path.isabs(job_top_dir):
		raise ArtifactReconciliationError('Unsafe job workspace root')
	workspace = workspace_for_job(job_top_dir, run['job_id'])
	if run.get('artifact_workspace') != workspace or not os.path.isdir(workspace) or os.path.islink(workspace):
		raise ArtifactReconciliationError('Run job workspace is missing or inconsistent')
	return run, workspace


def _discover(workspace, application, stage):
	description = JobConfigurator().get_app_description(application)
	if not isinstance(description, dict):
		raise ArtifactReconciliationError('Application has no output contract')
	contract = discovery.select_output_contract(description.get('job_outputs') or {}, stage)
	return discovery.discover_artifacts(workspace, contract)


def _plan(run, discovered):
	"""Keep original list unchanged; append only new regular-file outputs."""
	existing = run['artifacts']
	old_by_path = {}
	for item in existing:
		path = item['relative_path']
		if path in old_by_path:
			raise ArtifactReconciliationError('Duplicate registered artifact path')
		old_by_path[path] = item
	seen = set()
	missing = []
	for item in discovered:
		path = item['relative_path']
		if path in seen:
			raise ArtifactReconciliationError('Duplicate discovered artifact path')
		seen.add(path)
		previous = old_by_path.get(path)
		if previous is not None:
			for key in ('kind', 'size_bytes', 'file_count', 'directory_count'):
				if previous.get(key, 'file' if key == 'kind' else None) != item.get(key, 'file' if key == 'kind' else None):
					raise ArtifactReconciliationError('Previously registered artifact changed: %s' % path)
			continue
		if item.get('kind', 'file') != 'file':
			raise ArtifactReconciliationError('New directory artifacts require separate recovery: %s' % path)
		missing.append(item)
	return missing


def reconcile_retained_run(db, owner, pipeline_id, node_id, run_id, root,
		dry_run=True, max_file_bytes=1024 * 1024 * 1024,
		max_directory_bytes=1024 * 1024 * 1024 * 1024,
		max_directory_entries=100000, max_directory_depth=16):
	"""Recover newly declared file artifacts, atomically publishing both arrays.

	The existing retention lock serializes this operation with ordinary mixed
	retention. Prepared-but-uncommitted new files are checksum-verified on retry.
	Dry-run verifies discovery and metadata without writing run state.
	"""
	for limit in (max_file_bytes, max_directory_bytes,
			max_directory_entries, max_directory_depth):
		if type(limit) is not int or limit < 1:
			raise ArtifactReconciliationError('Invalid reconciliation limit')
	run, workspace = _load_verified_run(db, owner, pipeline_id, node_id, run_id)
	base = retention.retained_directory(root, owner, pipeline_id, run_id)
	if not os.path.isdir(base) or os.path.islink(base):
		raise ArtifactReconciliationError('Retained directory is unavailable')

	# The existing lock must already exist for mixed file/directory runs.
	base_fd = directory_retention._open_directory(base)
	try:
		fd = os.open('.retention.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=base_fd)
	except BaseException:
		os.close(base_fd)
		raise
	try:
		if not stat.S_ISREG(os.fstat(fd).st_mode):
			raise ArtifactReconciliationError('Invalid retention lock')
		fcntl.flock(fd, fcntl.LOCK_EX)
		run, workspace = _load_verified_run(db, owner, pipeline_id, node_id, run_id)
		_check_existing(db, owner, run, base, root, max_directory_bytes,
			max_directory_entries, max_directory_depth)
		discovered = _discover(workspace, run['application'],
			(run.get('parameters') or {}).get('stage'))
		missing = _plan(run, discovered)
		original_count = len(run['artifacts'])
		outcome = {
			'run_id': run_id, 'existing': original_count,
			'additional': len(missing), 'total': original_count + len(missing),
			'dry_run': bool(dry_run),
			'new_artifacts': [{'index': original_count + i,
				'name': item.get('name'), 'relative_path': item['relative_path']}
				for i, item in enumerate(missing)]
		}
		if not missing or dry_run:
			return outcome

		# Create an in-memory run with the proposed registrations, WITHOUT a
		# retained_artifacts field, so the source reader uses the trusted job.
		transient = dict(run)
		transient['artifacts'] = list(run['artifacts']) + missing
		transient.pop('retained_artifacts', None)
		new_records = []
		for position, item in enumerate(missing):
			index = original_count + position
			target = os.path.join(base, '%04d' % index)
			if os.path.lexists(target):
				record = resume.reuse_file(db, owner, transient, index,
					item, base, max_file_bytes)
			else:
				record = directory_promotion._copy_file(db, owner, transient,
					index, item, base, max_file_bytes)
			new_records.append(record)

		# Compare-and-set: never overwrite a changed run or a concurrent update.
		query = {
			'_id': run['_id'], 'owner': owner, 'pipeline_id': pipeline_id,
			'node_id': node_id, 'run_id': run_id,
			'job_id': run['job_id'], 'status': 'COMPLETED',
			'artifacts': run['artifacts'],
			'retained_artifacts': run['retained_artifacts'],
			'artifacts_registered_at': run['artifacts_registered_at'],
		}
		updated = db.pipeline_runs.update_one(query, {'$set': {
			'artifacts': transient['artifacts'],
			'retained_artifacts': list(run['retained_artifacts']) + new_records,
			'retention_status': 'READY',
			'artifacts_reconciled_at': manager.utcnow(),
		}})
		if updated.modified_count != 1:
			raise ArtifactReconciliationError('Concurrent update; rerun reconciliation')
		outcome['dry_run'] = False
		outcome['committed'] = True
		return outcome
	finally:
		os.close(fd)
		os.close(base_fd)
