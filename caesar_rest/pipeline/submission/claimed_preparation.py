"""Claim a frozen-input downstream run before preparing V2 worker assets.

No scheduler operation. A successful return leaves the run SUBMITTING and
returns an internal claim object for the next trusted submission step.
"""
from caesar_rest.pipeline import manager
from caesar_rest.pipeline.submission import job_binding
from caesar_rest.pipeline.submission import v2_preparation as preparation


def claim_and_prepare_v2(
	db, 
	owner, 
	pipeline_id, 
	node_id, 
	run_id, 
	job_id,
	job_root_app, 
	job_root_cluster, 
	retention_root_app,
	retention_root_cluster, 
	image, 
	arguments, 
	input_options,
	max_directory_bytes=1024 * 1024 * 1024 * 1024,
	max_directory_entries=100000, 
	max_directory_depth=16,
	dataset_app_root=None,
	dataset_cluster_root=None,
	dataset_input_name='measurement_set'
):
	"""Atomically claim a planned run, then prepare assets under its token.

	The trusted caller supplies paths, approved image/arguments/options, and
	a server-generated job_id. It must never return this result to REST clients.
	Preparation failure marks the claimed run SUBMISSION_FAILED (not PLANNED).
	"""
	manager.validate_identifier(node_id, 'node_id')
	manager.get_pipeline(owner, pipeline_id)
	run = db.pipeline_runs.find_one({
		'owner': owner, 'pipeline_id': pipeline_id,
		'node_id': node_id, 'run_id': run_id, 'status': 'PLANNED'
	})
	
	if run is None:
		raise manager.PipelineError('PLANNED V2 run not found', 409)

	if not isinstance(run.get('input_artifacts'), list):
		raise manager.PipelineError('Invalid frozen artifact inputs', 409)

	if not run['input_artifacts'] and run.get('dataset_id') is None:
		raise manager.PipelineError('V2 run has no inputs', 409)	

	claim = job_binding.claim_run(
		owner, pipeline_id, run_id, run['application'],
		run.get('parameters') or {},
		dataset_id=run.get('dataset_id'),
		require_dataset_binding=(run.get('dataset_id') is not None)
	)

	try:
		assets = preparation.prepare_v2_submission(
			db, owner, pipeline_id, node_id, run_id, job_id,
			job_root_app, job_root_cluster, retention_root_app,
			retention_root_cluster, image, arguments, input_options,
			max_directory_bytes=max_directory_bytes,
			max_directory_entries=max_directory_entries,
			max_directory_depth=max_directory_depth,
			submission_token=claim.token,
			dataset_app_root=dataset_app_root,
			dataset_cluster_root=dataset_cluster_root,
			dataset_input_name=dataset_input_name
		)
	except Exception:
		# No scheduler call has occurred. Do not retry/revert to PLANNED;
		# the workspace (if created) is preserved for investigation.
		job_binding.fail_submission(claim, 'V2 preparation failed', uncertain=False, job_id=job_id)
		raise
	return {'claim': claim, 'assets': assets}
