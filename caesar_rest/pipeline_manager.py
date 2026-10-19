"""Application-independent pipeline and scientific run metadata.

Runs are reservations, not scheduler jobs. Submission and artifact publishing
will be attached in a later integration step. All reads are owner-scoped.
"""

import datetime
import re
import uuid

from pymongo import ReturnDocument

from caesar_rest import mongo


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


def get_pipeline(owner, pipeline_id):
	pipelines, _, _ = collections()
	doc = pipelines.find_one({'pipeline_id': pipeline_id, 'owner': owner})
	if doc is None:
		raise PipelineError('Pipeline not found', 404)
	return doc


def create_pipeline(owner, payload):
	if not isinstance(payload, dict):
		raise PipelineError('Expected a JSON object')
	if set(payload) - {'name', 'description', 'metadata'}:
		raise PipelineError('Unsupported pipeline field')
	name = payload.get('name', '')
	description = payload.get('description', '')
	metadata = payload.get('metadata', {})
	if not isinstance(name, str) or len(name) > 200:
		raise PipelineError('Invalid pipeline name')
	if not isinstance(description, str) or len(description) > 2000:
		raise PipelineError('Invalid pipeline description')
	if not isinstance(metadata, dict):
		raise PipelineError('metadata must be an object')
	pipelines, _, _ = collections()
	doc = {
		'pipeline_id': uuid.uuid4().hex,
		'owner': owner,
		'name': name,
		'description': description,
		'metadata': metadata,
		'created_at': utcnow(),
		'status': 'ACTIVE',
		'selections': {}
	}
	pipelines.insert_one(doc)
	return public_doc(doc)


def list_pipelines(owner):
	pipelines, _, _ = collections()
	return [public_doc(doc) for doc in pipelines.find({'owner': owner}).sort('created_at', -1)]


def create_run(owner, pipeline_id, node_id, payload):
	"""Reserve a distinct experiment. Does NOT submit anything to Slurm."""
	validate_identifier(node_id, 'node_id')
	get_pipeline(owner, pipeline_id)
	if not isinstance(payload, dict):
		raise PipelineError('Expected a JSON object')
	
	if set(payload) - {
		'application', 'operation', 'parameters',
		'input_runs', 'dataset_id'
	}:
		raise PipelineError('Unsupported run field')
			
	application = validate_identifier(payload.get('application'), 'application')
	operation = validate_identifier(payload.get('operation'), 'operation')
	parameters = payload.get('parameters', {})
	input_runs = payload.get('input_runs', [])
	
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
		'dataset_id': dataset_id,
		'status': 'PLANNED',
		'job_id': None,
		'artifacts': [],
		'created_at': utcnow()
	}
	runs.insert_one(doc)
	return public_doc(doc)


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
