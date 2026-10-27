"""Application-independent pipeline and scientific run metadata.

Runs are reservations, not scheduler jobs. Submission and artifact publishing
will be attached in a later integration step. All reads are owner-scoped.
"""

import datetime
import re
import uuid
import time

from pymongo import ReturnDocument

from caesar_rest import mongo
from caesar_rest import logger

IDENTIFIER_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
RUN_STATES = {
	'PLANNED',
	'SUBMITTING',
	'SUBMITTED',
	'SUBMISSION_FAILED',
	'SUBMISSION_UNCERTAIN',
	'RUNNING',
	'COMPLETED',
	'FAILED',
	'CANCELLED'
}

class PipelineError(Exception):
	"""A validation or state error with an HTTP status code."""

	def __init__(self, message, status=400):
		super().__init__(message)
		self.status = status


def utcnow():
	return datetime.datetime.now(datetime.timezone.utc)


def collections():
	"""Return collections from the Flask application's configured MongoDB."""
	if mongo is None or mongo.db is None:
		raise PipelineError('MongoDB is not configured', 503)
	return mongo.db.pipelines, mongo.db.pipeline_runs, mongo.db.pipeline_counters


def public_doc(doc):
	"""Never return MongoDB internal identifiers to API clients."""
	if doc is None:
		return None
	return {key: value for key, value in doc.items() if key != '_id' and key != 'owner'}


def ensure_indexes():
	"""Call at deployment initialization, not during each request."""
	pipelines, runs, counters = collections()
	pipelines.create_index([('pipeline_id', 1)], unique=True)
	runs.create_index([('run_id', 1)], unique=True)
	runs.create_index([('pipeline_id', 1), ('node_id', 1), ('sequence', 1)], unique=True)
	counters.create_index([('pipeline_id', 1), ('node_id', 1)], unique=True)


def validate_identifier(value, field):
	if not isinstance(value, str) or IDENTIFIER_RE.fullmatch(value) is None:
		raise PipelineError('%s must match %s' % (field, IDENTIFIER_RE.pattern))
	return value

def default_node_id(stage):
	"""Derive a stable, generic experiment-group ID from a stage."""

	if not isinstance(stage, str) or not stage:
		raise PipelineError('Invalid scientific stage')

	node_id = 'stage_' + stage.lower()

	return validate_identifier(node_id, 'node_id')


def validate_pipeline_stage(app, stage):
	"""Validate a stage against the configured V2 application policy."""

	from flask import current_app

	app = validate_identifier(app, 'app')

	if not isinstance(stage, str) or not stage:
		raise PipelineError('stage must be a nonempty string')

	policies = current_app.config.get('PIPELINE_V2_APPLICATIONS', {})

	if not isinstance(policies, dict):
		raise PipelineError('Invalid V2 application configuration', 503)

	policy = policies.get(app)

	if not isinstance(policy, dict):
		raise PipelineError('Application is not enabled for V2', 409)

	parameters = policy.get('parameters')

	if not isinstance(parameters, dict):
		raise PipelineError('Invalid V2 parameter policy', 503)

	stages = parameters.get('stage')

	if not isinstance(stages, (list, tuple)) or not stages:
		raise PipelineError('Application has no configured stages', 503)

	if stage not in stages:
		raise PipelineError('Unsupported scientific stage', 400)

	input_policies = policy.get('input_options_by_stage')

	if input_policies is not None:
		if not isinstance(input_policies, dict):
			raise PipelineError('Invalid V2 stage input policy', 503)

		if stage not in input_policies:
			raise PipelineError(
				'Scientific stage has no V2 input policy', 409
			)

	return stage


def get_pipeline_app(pipeline):
	"""Return the authoritative application of a pipeline."""

	app = pipeline.get('app')

	if app is not None:
		return validate_identifier(app, 'app')

	# Compatibility with pipelines created before the API refactor.
	metadata = pipeline.get('metadata') or {}

	if not isinstance(metadata, dict):
		raise PipelineError('Invalid legacy pipeline metadata', 409)

	app = metadata.get('application')

	if app is None:
		raise PipelineError(
			'Legacy pipeline has no application; create a new pipeline '
			'or use the legacy run registration endpoint',
			409
		)

	return validate_identifier(app, 'app')

def get_pipeline(owner, pipeline_id):
	pipelines, _, _ = collections()
	doc = pipelines.find_one({'pipeline_id': pipeline_id, 'owner': owner})
	if doc is None:
		raise PipelineError('Pipeline not found', 404)
	return doc


def create_pipeline(owner, payload):
	"""Create a pipeline with an authoritative V2 application."""

	if not isinstance(payload, dict):
		raise PipelineError('Expected a JSON object')

	if set(payload) - {'app', 'name', 'description', 'metadata'}:
		raise PipelineError('Unsupported pipeline field')

	app = validate_identifier(payload.get('app'), 'app')

	from flask import current_app

	policies = current_app.config.get('PIPELINE_V2_APPLICATIONS', {})

	if not isinstance(policies, dict):
		raise PipelineError('Invalid V2 application configuration', 503)

	if app not in policies or not isinstance(policies[app], dict):
		raise PipelineError('Application is not enabled for V2', 409)

	name = payload.get('name', '')
	description = payload.get('description', '')
	metadata = payload.get('metadata', {})

	if not isinstance(name, str) or len(name) > 200:
		raise PipelineError('Invalid pipeline name')

	if not isinstance(description, str) or len(description) > 2000:
		raise PipelineError('Invalid pipeline description')

	if not isinstance(metadata, dict):
		raise PipelineError('metadata must be an object')

	if 'application' in metadata or 'app' in metadata:
		raise PipelineError(
			'Specify the application using the top-level app field'
		)

	pipelines, _, _ = collections()

	doc = {
		'pipeline_id': uuid.uuid4().hex,
		'owner': owner,
		'app': app,
		'name': name,
		'description': description,
		'metadata': metadata,
		'node_stages': {},
		'created_at': utcnow(),
		'status': 'ACTIVE',
		'selections': {}
	}

	pipelines.insert_one(doc)

	return public_doc(doc)
	


def list_pipelines(owner):
	pipelines, _, _ = collections()
	return [public_doc(doc) for doc in pipelines.find({'owner': owner}).sort('created_at', -1)]


def establish_node_stage(owner, pipeline_id, node_id, stage):
	"""Bind a logical node to exactly one scientific stage."""

	validate_identifier(node_id, 'node_id')

	if not isinstance(stage, str) or not stage:
		raise PipelineError('Invalid scientific stage')

	pipelines, runs, _ = collections()

	# Existing nodes may predate persisted node-stage associations.
	legacy = runs.find_one({
		'owner': owner,
		'pipeline_id': pipeline_id,
		'node_id': node_id,
		'parameters.stage': {'$ne': stage}
	})

	if legacy is not None:
		raise PipelineError(
			'Node already contains a different scientific stage',
			409
		)

	field = 'node_stages.' + node_id

	result = pipelines.update_one(
		{
			'owner': owner,
			'pipeline_id': pipeline_id,
			'$or': [
				{field: {'$exists': False}},
				{field: stage}
			]
		},
		{
			'$set': {
				field: stage
			}
		}
	)

	if result.matched_count != 1:
		raise PipelineError(
			'Node is already associated with a different stage',
			409
		)

def create_run(
	owner, 
	pipeline_id, 
	node_id, 
	payload, 
	retention_root='',
	max_directory_bytes=1024 * 1024 * 1024 * 1024,
	max_directory_entries=100000, 
	max_directory_depth=16
):
	"""Reserve a distinct experiment. Does NOT submit anything to Slurm."""
	
	t_run = time.perf_counter()
	
	validate_identifier(node_id, 'node_id')
	get_pipeline(owner, pipeline_id)
	if not isinstance(payload, dict):
		raise PipelineError('Expected a JSON object')
	
	if set(payload) - {
		'application', 'operation', 'parameters',
		'input_runs', 'input_artifacts', 'dataset_id'
	}:
		raise PipelineError('Unsupported run field')
			
	application = validate_identifier(payload.get('application'), 'application')
	operation = validate_identifier(payload.get('operation'), 'operation')
	parameters = payload.get('parameters', {})
	input_runs = payload.get('input_runs', [])
	input_artifacts = payload.get('input_artifacts', [])
	
	if not isinstance(parameters, dict):
		raise PipelineError('parameters must be an object')

	stage = parameters.get('stage')

	if stage is not None:
		if not isinstance(stage, str) or not stage:
			raise PipelineError('Invalid parameters.stage')
	
	dataset_id = payload.get('dataset_id')

	if dataset_id is not None:
		from caesar_rest import dataset_registry

		if not isinstance(dataset_id, str):
			raise PipelineError('dataset_id must be a string')

		try:
			dataset_registry.resolve_input_dataset(dataset_id)
		except dataset_registry.DatasetError as exc:
			raise PipelineError(str(exc), exc.status)
	
	if not isinstance(parameters, dict) or not isinstance(input_runs, list):
		raise PipelineError('parameters must be an object and input_runs a list')
	
	if len(input_runs) != len(set(str(x) for x in input_runs)):
		raise PipelineError('Duplicate parent run reference')
	_, runs, counters = collections()
	
	for parent_id in input_runs:
		if not isinstance(parent_id, str):
			raise PipelineError('input_runs must contain run IDs')
		parent = runs.find_one({'run_id': parent_id, 'pipeline_id': pipeline_id, 'owner': owner})
		if parent is None or parent['status'] != 'COMPLETED':
			raise PipelineError('Input run must exist and be completed: %s' % parent_id, 409)
	
	# Import lazily to avoid circular dependencies:
	# artifacts.binding -> artifacts.access -> pipeline.manager.
	from caesar_rest.pipeline.artifacts import binding as pipeline_artifact_binding

	t_bind = time.perf_counter()
	
	bindings = pipeline_artifact_binding.bind_inputs(
		mongo.db,
		owner,
		pipeline_id,
		input_artifacts,
		retention_root,
		max_directory_bytes=max_directory_bytes,
		max_directory_entries=max_directory_entries,
		max_directory_depth=max_directory_depth
	)
	
	logger.info(
		'V2 run registration artifact binding: '
		'pipeline_id=%s node_id=%s elapsed=%.3fs',
		pipeline_id,
		node_id,
		time.perf_counter() - t_bind
	)

	bound_run_ids = {item['source_run_id'] for item in bindings}

	if not bound_run_ids.issubset(set(input_runs)):
		raise PipelineError(
			'Every bound source_run_id must also appear in input_runs',
			400
		)
	
	if stage is not None:
		establish_node_stage(
			owner,
			pipeline_id,
			node_id,
			stage
		)	
	
	t_database = time.perf_counter()
	
	counter = counters.find_one_and_update(
		{'pipeline_id': pipeline_id, 'node_id': node_id},
		{'$inc': {'sequence': 1}},
		upsert=True,
		return_document=ReturnDocument.AFTER
	)
	
	sequence = counter['sequence']
	
	doc = {
		'run_id': uuid.uuid4().hex,
		'pipeline_id': pipeline_id,
		'owner': owner,
		'node_id': node_id,
		'run_name': 'run%03d' % sequence,
		'sequence': sequence,
		'application': application,
		'operation': operation,
		'parameters': parameters,
		'input_runs': list(input_runs),
		'input_artifacts': bindings,
		'dataset_id': dataset_id,
		'status': 'PLANNED',
		'job_id': None,
		'artifacts': [],
		'created_at': utcnow()
	}
	runs.insert_one(doc)
	
	logger.info(
		'V2 run registration database finalization: '
		'pipeline_id=%s node_id=%s elapsed=%.3fs',
		pipeline_id,
		node_id,
		time.perf_counter() - t_database
	)
	
	logger.info(
		'V2 run registration total: '
		'pipeline_id=%s node_id=%s elapsed=%.3fs',
		pipeline_id,
		node_id,
		time.perf_counter() - t_run
	)

	return public_doc(doc)


def create_run_simple(
	owner,
	pipeline_id,
	payload,
	retention_root='',
	max_directory_bytes=1024 * 1024 * 1024 * 1024,
	max_directory_entries=100000,
	max_directory_depth=16
):
	"""Register a V2 run using stage and optional experiment-group ID."""

	if not isinstance(payload, dict):
		raise PipelineError('Expected a JSON object')

	allowed = {
		'stage',
		'node_id',
		'parameters',
		'dataset_id',
		'input_artifacts'
	}

	if set(payload) - allowed:
		raise PipelineError('Unsupported run field')

	pipeline = get_pipeline(owner, pipeline_id)

	app = get_pipeline_app(pipeline)

	stage = validate_pipeline_stage(
		app,
		payload.get('stage')
	)

	node_id = payload.get('node_id')

	if node_id is None:
		node_id = default_node_id(stage)
	else:
		validate_identifier(node_id, 'node_id')

	parameters = payload.get('parameters', {})

	if not isinstance(parameters, dict):
		raise PipelineError('parameters must be an object')

	if 'stage' in parameters:
		raise PipelineError(
			'stage must not be repeated inside parameters'
		)

	# Preserve the existing V2 submission/configurator interface.
	execution_parameters = dict(parameters)
	execution_parameters['stage'] = stage

	input_artifacts = payload.get('input_artifacts', [])

	if not isinstance(input_artifacts, list):
		raise PipelineError('input_artifacts must be a list')

	input_runs = set()

	for item in input_artifacts:
		if not isinstance(item, dict):
			raise PipelineError('Invalid input artifact reference')

		source_run_id = item.get('source_run_id')

		if not isinstance(source_run_id, str) or not source_run_id:
			raise PipelineError('Invalid source_run_id')

		input_runs.add(source_run_id)

	legacy_payload = {
		'application': app,
		'operation': default_node_id(stage),
		'parameters': execution_parameters,
		'input_runs': sorted(input_runs),
		'input_artifacts': input_artifacts
	}

	if 'dataset_id' in payload:
		legacy_payload['dataset_id'] = payload['dataset_id']

	return create_run(
		owner,
		pipeline_id,
		node_id,
		legacy_payload,
		retention_root=retention_root,
		max_directory_bytes=max_directory_bytes,
		max_directory_entries=max_directory_entries,
		max_directory_depth=max_directory_depth
	)

def list_runs(owner, pipeline_id, node_id=None):
	get_pipeline(owner, pipeline_id)
	_, runs, _ = collections()
	query = {'owner': owner, 'pipeline_id': pipeline_id}
	if node_id is not None:
		validate_identifier(node_id, 'node_id')
		query['node_id'] = node_id
	return [public_doc(doc) for doc in runs.find(query).sort([('node_id', 1), ('sequence', 1)])]


def select_run(owner, pipeline_id, node_id, run_id):
	"""Atomically record preferred completed run; never dispatch next stage."""
	validate_identifier(node_id, 'node_id')
	pipelines, runs, _ = collections()
	get_pipeline(owner, pipeline_id)
	run = runs.find_one({'owner': owner, 'pipeline_id': pipeline_id, 'node_id': node_id, 'run_id': run_id})
	if run is None:
		raise PipelineError('Run not found', 404)
	if run['status'] != 'COMPLETED':
		raise PipelineError('Only completed runs can be selected', 409)
	pipelines.update_one(
		{'owner': owner, 'pipeline_id': pipeline_id},
		{'$set': {'selections.' + node_id: {'run_id': run_id, 'selected_at': utcnow()}}}
	)
	return {'node_id': node_id, 'run_id': run_id}
	
def get_pipeline_tree(owner, pipeline_id):
	"""Build an owner-scoped logical tree from existing pipeline/run metadata.

	No filesystem access, scheduler calls, or database modifications.
	Internal workspace paths and MongoDB identifiers are never exposed.
	"""
	pipeline = get_pipeline(owner, pipeline_id)
	_, runs_collection, _ = collections()

	selections = pipeline.get('selections') or {}
	nodes = {}

	cursor = runs_collection.find({
		'owner': owner,
		'pipeline_id': pipeline_id
	}).sort([
		('node_id', 1),
		('sequence', 1)
	])

	for run in cursor:
		node_id = run['node_id']

		if node_id not in nodes:
			selection = selections.get(node_id) or {}
			node_stages = pipeline.get('node_stages') or {}
			stage = node_stages.get(node_id)

			if stage is None:
				stage = (run.get('parameters') or {}).get('stage')

			nodes[node_id] = {
				'node_id': node_id,
				'stage': stage,
				'selected_run_id': selection.get('run_id'),
				'runs': []
			}

		artifacts = run.get('artifacts') or []
		primary_count = sum(
			1 for artifact in artifacts
			if artifact.get('role') == 'primary_result'
		)

		nodes[node_id]['runs'].append({
			'run_id': run['run_id'],
			'run_name': run['run_name'],
			'sequence': run['sequence'],
			'application': run['application'],
			'operation': run['operation'],
			'parameters': run.get('parameters') or {},
			'dataset_id': run.get('dataset_id'),
			'input_runs': run.get('input_runs') or [],
			'input_artifacts': run.get('input_artifacts') or [],
			'status': run['status'],
			'job_id': run.get('job_id'),
			'created_at': run.get('created_at'),
			'finished_at': run.get('finished_at'),
			'artifact_summary': {
				'registered': bool(run.get('artifacts_registered_at')),
				'count': len(artifacts),
				'primary_count': primary_count
			},
			'selected': (
				run['run_id'] == nodes[node_id]['selected_run_id']
			)
		})

	return {
		'pipeline_id': pipeline_id,
		'name': pipeline.get('name', ''),
		'description': pipeline.get('description', ''),
		'status': pipeline.get('status'),
		'created_at': pipeline.get('created_at'),
		'nodes': [
			nodes[node_id]
			for node_id in sorted(nodes)
		]
	}
