"""Prepare V2 worker assets for one owner-scoped PLANNED pipeline run.

No Slurm operations, submission claim, database mutations, or client paths.
The caller supplies server-generated job_id, trusted roots and validated app args.
A failed preparation leaves its exclusive workspace for inspection.
"""
import os
import re
from pathlib import Path

from caesar_rest import pipeline_manager as manager
from caesar_rest import pipeline_v2_submission_adapter as adapter
from caesar_rest.pipeline.staging import submission_specs as spec_writer
from caesar_rest import pipeline_worker_bundle as worker_bundle

_JOB_ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def _canonical_root(value, label):
	if (not isinstance(value, str) or not os.path.isabs(value)
			or value == '/' or os.path.normpath(value) != value
			or '//' in value or any(p in ('.', '..') for p in value.split('/'))):
		raise manager.PipelineError('Invalid configured ' + label, 503)
	return value


def _trusted_directory(path):
	"""Walk the complete directory path without traversing symlinks."""
	fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
	try:
		for component in path.split('/'):
			if component:
				new = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
				os.close(fd)
				fd = new
	finally:
		os.close(fd)


def prepare_v2_submission(db, owner, pipeline_id, node_id, run_id, job_id,
		job_root_app, job_root_cluster, retention_root_app,
		retention_root_cluster, image, arguments, input_options,
		max_directory_bytes=1024 * 1024 * 1024 * 1024,
		max_directory_entries=100000, max_directory_depth=16,
		submission_token=None):
	"""Create one fresh workspace with trusted V2 specs and isolated worker.

	Returns *internal* workspace and asset paths for a subsequent trusted
	submission step. Do not expose the returned mapping through a REST route.
	No state transition is performed; the run remains PLANNED.
	"""
	if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
		raise manager.PipelineError('Invalid server-generated job identifier', 409)
	manager.validate_identifier(node_id, 'node_id')
	manager.get_pipeline(owner, pipeline_id)
	
	query = {
		'owner': owner,
		'pipeline_id': pipeline_id,
		'node_id': node_id,
		'run_id': run_id
	}

	if submission_token is None:
		# Preserve the original preparation-only behavior.
		query['status'] = 'PLANNED'
	else:
		# Only the request holding the active submission claim
		# may prepare this run.
		if (
			not isinstance(submission_token, str)
			or not re.fullmatch(r'[0-9a-f]{32}', submission_token)
		):
			raise manager.PipelineError('Invalid submission claim token', 409)

		query['status'] = 'SUBMITTING'
		query['submission_token'] = submission_token

	run = db.pipeline_runs.find_one(query)

	if run is None:
		raise manager.PipelineError(
			'Downstream run not available for V2 preparation', 409
		)
	
	
	if not run.get('input_artifacts'):
		raise manager.PipelineError('Downstream run has no frozen inputs', 409)

	app_root = _canonical_root(job_root_app, 'application job root')
	cluster_root = _canonical_root(job_root_cluster, 'cluster job root')
	app_ws = os.path.join(app_root, 'job_' + job_id)
	cluster_ws = os.path.join(cluster_root, 'job_' + job_id)
	try:
		_trusted_directory(app_root)
		if os.path.lexists(app_ws):
			raise manager.PipelineError('V2 preparation workspace already exists', 409)
		# The directory claim is atomic. Never reuse or overwrite a job directory.
		os.mkdir(app_ws, 0o700)
		_trusted_directory(app_ws)
	except manager.PipelineError:
		raise
	except FileExistsError as exc:
		raise manager.PipelineError('V2 preparation workspace already exists', 409) from exc
	except OSError as exc:
		raise manager.PipelineError('Cannot create private V2 workspace', 503) from exc

	try:
		
		staging, execution = adapter.build_bound_v2_specs(
			db,
			owner,
			run,
			retention_root_app,
			retention_root_cluster,
			cluster_ws,
			image,
			arguments,
			input_options,
			max_directory_bytes=max_directory_bytes,
			max_directory_entries=max_directory_entries,
			max_directory_depth=max_directory_depth,
			submission_token=submission_token
		)		
		
		if staging.get('version') != 2 or execution.get('version') != 2:
			raise manager.PipelineError('Unexpected specification version', 409)
		spec_paths = spec_writer.write_specs(app_ws, staging, execution)
		worker = worker_bundle.deploy_worker(app_ws)
		return {
			'run_id': run_id, 'job_id': job_id,
			'workspace_app': app_ws, 'workspace_cluster': cluster_ws,
			'staging_spec_app': spec_paths[0], 'execution_spec_app': spec_paths[1],
			'staging_spec_cluster': os.path.join(cluster_ws, 'staging_spec.json'),
			'execution_spec_cluster': os.path.join(cluster_ws, 'execution_spec.json'),
			'worker_cluster': os.path.join(cluster_ws, worker['name']),
			'worker_sha256': worker['sha256'], 'version': 2
		}
	except manager.PipelineError:
		raise
	except (ValueError, OSError) as exc:
		# Preserve partial workspace for explicit administrative investigation.
		raise manager.PipelineError('V2 preparation failed; inspect reserved workspace', 503) from exc
