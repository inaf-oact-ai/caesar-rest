"""Opt-in V2 pipeline submission from the existing authenticated /job route.

No user-controlled storage paths or execution specifications. Only server
configuration maps frozen parameters and input names into application options.
"""
import datetime
import re
import time

from flask import current_app

from caesar_rest import mongo, jobmgr_slurm, utils
from caesar_rest.pipeline import manager
from caesar_rest.pipeline.submission.claimed_preparation import claim_and_prepare_v2
from caesar_rest.pipeline.submission.slurm_submission import submit_claimed_v2
from caesar_rest.job_configurator import JobConfigurator

_OPTION = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
_VALUE = re.compile(r'^[A-Za-z0-9_.:+/-]{1,128}$')


def _validated_arguments(parameters, allowed):
	"""Produce arguments exclusively from an administrator-controlled allowlist."""
	if not isinstance(parameters, dict) or not isinstance(allowed, dict):
		raise manager.PipelineError('Invalid V2 parameter policy', 503)
	if set(parameters) != set(allowed):
		raise manager.PipelineError('V2 run parameters do not match application policy', 409)
	args = []
	for option in sorted(allowed):
		values = allowed[option]
		value = parameters[option]
		if (not _OPTION.fullmatch(option)
				or not isinstance(values, (list, tuple))
				or not values
				or not isinstance(value, str)
				or not _VALUE.fullmatch(value)
				or value not in values):
			raise manager.PipelineError('Unsupported V2 scientific parameter', 409)
		args.append('--%s=%s' % (option, value))
	return args


def submit_v2(owner, request_data, resolve_application):
	"""Claim, prepare, and submit an artifact-only V2 run.

	Return the ordinary /job response shape plus an internal job record.
	After Slurm acceptance, never retry or undo the durable submission intent.
	"""
	if not isinstance(request_data, dict):
		raise manager.PipelineError('Invalid V2 request', 400)
	required = {'app', 'pipeline_id', 'node_id', 'run_id', 'job_options',
		'submission_version'}
	if set(request_data) != required or request_data['submission_version'] != 2:
		raise manager.PipelineError('Invalid V2 request fields', 400)

	app = request_data['app']
	pipeline_id = request_data['pipeline_id']
	node_id = request_data['node_id']
	run_id = request_data['run_id']
	options = request_data['job_options']
	if not all(isinstance(x, str) and x for x in (app, pipeline_id, node_id, run_id)):
		raise manager.PipelineError('Invalid V2 identifiers', 400)
	manager.validate_identifier(node_id, 'node_id')
	manager.get_pipeline(owner, pipeline_id)
	run = mongo.db.pipeline_runs.find_one({
		'owner': owner, 'pipeline_id': pipeline_id, 'node_id': node_id,
		'run_id': run_id, 'status': 'PLANNED'
	})
	
	if run is None:
		raise manager.PipelineError('PLANNED pipeline run not found', 409)
	
	if run.get('application') != app or run.get('parameters') != options:
		raise manager.PipelineError('V2 request does not match reserved run', 409)
		
	if not isinstance(run.get('input_artifacts'), list):
		raise manager.PipelineError('Invalid frozen input list', 409)

	if not run['input_artifacts'] and run.get('dataset_id') is None:
		raise manager.PipelineError('V2 run has no inputs', 409)

	if current_app.config.get('JOB_SCHEDULER') != 'slurm':
		raise manager.PipelineError('V2 requires Slurm', 409)
	
	if not current_app.config.get('PIPELINE_STAGED_EXECUTION_ENABLED', False):
		raise manager.PipelineError('Staged execution disabled', 409)

	policies = current_app.config.get('PIPELINE_V2_APPLICATIONS', {})
	policy = policies.get(app) if isinstance(policies, dict) else None
	if not isinstance(policy, dict):
		raise manager.PipelineError('Application not enabled for V2', 409)
		
	input_options_by_stage = policy.get('input_options_by_stage')

	if input_options_by_stage is not None:
		if not isinstance(input_options_by_stage, dict):
			raise manager.PipelineError('Invalid stage input policy', 503)

		stage = run['parameters'].get('stage')
		input_options = input_options_by_stage.get(stage)
	else:
		input_options = policy.get('input_options')
	
	if not isinstance(input_options, dict) or not input_options:
		raise manager.PipelineError('Missing V2 input policy', 503)
	
	
	bound_names = {
		item.get('input_name')
		for item in run['input_artifacts']
	}

	dataset_input_name = policy.get(
		'dataset_input_name', 'measurement_set'
	)

	if run.get('dataset_id') is not None:
		if (
			not isinstance(dataset_input_name, str)
			or not _OPTION.fullmatch(dataset_input_name)
			or dataset_input_name in bound_names
		):
			raise manager.PipelineError(
				'Invalid or conflicting dataset input name', 409
			)

		bound_names.add(dataset_input_name)
	
	if (set(input_options.values()) != bound_names
			or len(input_options) != len(bound_names)
			or not all(isinstance(k, str) and _OPTION.fullmatch(k)
				for k in input_options)):
		raise manager.PipelineError('V2 input binding does not match policy', 409)

	# - Delegate application-specific scientific options to the registered
	#   configurator. The V2 submission layer remains application-agnostic.
	allowed_parameters = policy.get('parameters', {})

	configurator_class = JobConfigurator().app_configurators.get(app)

	try:
		if configurator_class is not None:
			configurator = configurator_class(app_name=app)
			args = configurator.build_pipeline_arguments(
				options,
				allowed_parameters,
				_validated_arguments
			)
		else:
			# - Preserve the existing behavior for V2 applications
			#   without an application configurator.
			args = _validated_arguments(options, allowed_parameters)
	except ValueError as exc:
		raise manager.PipelineError(
			'Invalid application scientific options: %s' % exc, 409
		) from exc

	if not args:
		raise manager.PipelineError(
			'V2 requires explicit configured arguments', 409
		)
		
	app_spec = resolve_application(app, 'slurm', {})
	image = app_spec['image']
	job_id = utils.get_uuid()
	job_root_app = jobmgr_slurm.app_jobdir
	job_root_cluster = jobmgr_slurm.cluster_jobdir
	owner_job_app = job_root_app.rstrip('/') + '/' + owner
	owner_job_cluster = job_root_cluster.rstrip('/') + '/' + owner
	retention_root_app = current_app.config.get('PIPELINE_ARTIFACT_RETENTION_ROOT')
	retention_root_cluster = current_app.config.get('PIPELINE_ARTIFACT_RETENTION_ROOT_CLUSTER')
	
	if run['input_artifacts']:
		if not retention_root_app or not retention_root_cluster:
			raise manager.PipelineError(
				'V2 retention roots are not configured', 503
			)

	# Preparation is responsible for claim failure persistence when needed
	t_prepare = time.perf_counter()
	
	prepared = claim_and_prepare_v2(
		mongo.db, owner, pipeline_id, node_id, run_id, job_id,
		owner_job_app, owner_job_cluster,
		retention_root_app, retention_root_cluster,
		image, args, input_options,
		max_directory_bytes=current_app.config.get(
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES', 1024 ** 4),
		max_directory_entries=current_app.config.get(
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES', 100000),
		max_directory_depth=current_app.config.get(
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH', 16),
		dataset_app_root=jobmgr_slurm.app_datadir,
		dataset_cluster_root=jobmgr_slurm.cluster_datadir,
		dataset_input_name=dataset_input_name
	)
	
	prepare_seconds = time.perf_counter() - t_prepare
	current_app.logger.info('V2 submission preparation: %.3f seconds', prepare_seconds)
	
	# This function manages one-shot scheduler intent and run finalization.
	t_scheduler = time.perf_counter()
	
	submitted = submit_claimed_v2(
		prepared, jobmgr_slurm, job_id,
		python_executable=current_app.config.get('PIPELINE_PYTHON_EXECUTABLE')
			or '/usr/bin/python3'
	)
	
	scheduler_seconds = time.perf_counter() - t_scheduler
	current_app.logger.info('V2 Slurm submission: %.3f seconds', scheduler_seconds)
	
	
	now = datetime.datetime.now().isoformat()
	workspace = prepared['assets']['workspace_app']
	job_doc = {
		'job_id': job_id, 'submit_date': now, 'app': app,
		'job_options': options, 'data_inputs': None,
		'job_top_dir': owner_job_app, 'metadata': '', 'tag': '',
		'scheduler': 'slurm', 'state': 'PENDING',
		'status': 'Job submitted', 'pid': submitted['scheduler_pid'],
		'elapsed_time': '0', 'exit_code': -1,
		'pipeline_id': pipeline_id, 'run_id': run_id,
		'execution_mode': 'staged_container',
		'workspace': workspace,
		'output_root': workspace + '/results',
		'output_layout': 'results_subdirectory_v2'
	}
	try:
		mongo.db[owner + '.jobs'].insert_one(job_doc)
	except Exception as exc:
		# Slurm accepted this job: never mark it failed or retry submission.
		raise manager.PipelineError(
			'Slurm accepted V2 job but job registration failed; reconcile manually',
			503
		) from exc
	return {
		'job_id': job_id, 'pid': submitted['scheduler_pid'],
		'submit_date': now, 'state': 'PENDING',
		'status': 'Job submitted to Slurm scheduler', 'app': app
	}
