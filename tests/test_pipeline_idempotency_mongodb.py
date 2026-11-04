
"""MongoDB-backed Pipeline V2 idempotency and concurrency tests.

Requires a dedicated MongoDB test instance. Never use the production
CAESAR-REST database or application credentials.

No scientific processing, filesystem artifacts or Slurm submission.
"""

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from flask import Flask
from pymongo import MongoClient
from pymongo.errors import AutoReconnect

from caesar_rest.pipeline import manager
from caesar_rest.pipeline import idempotency
from caesar_rest.pipeline.artifacts import binding


@pytest.fixture
def mongo_context(monkeypatch):
	"""Create and clean up an isolated MongoDB test database."""

	uri = os.environ.get('CAESAR_IDEMPOTENCY_TEST_URI')

	if (
		not uri
		or os.environ.get(
			'CAESAR_IDEMPOTENCY_ALLOW_TEST_DB'
		) != 'YES'
	):
		pytest.skip(
			'Dedicated MongoDB test URI and explicit opt-in required'
		)

	client = MongoClient(
		uri,
		serverSelectionTimeoutMS=3000,
		retryWrites=False
	)

	client.admin.command('ping')

	database_name = (
		'caesar_idempotency_test_'
		+ uuid.uuid4().hex
	)

	db = client[database_name]

	class MongoProxy:
		pass

	proxy = MongoProxy()
	proxy.db = db

	monkeypatch.setattr(manager, 'mongo', proxy)

	monkeypatch.setattr(
		manager,
		'get_pipeline',
		lambda owner, pipeline_id: {
			'owner': owner,
			'pipeline_id': pipeline_id,
			'app': 'oxkat',
			'dataset_id': None
		}
	)

	# This suite tests registration persistence, not node-stage CAS.
	monkeypatch.setattr(
		manager,
		'establish_node_stage',
		lambda *args, **kwargs: None
	)

	# No real upstream artifacts are involved in these tests.
	monkeypatch.setattr(
		binding,
		'bind_inputs',
		lambda *args, **kwargs: []
	)

	manager.ensure_indexes()

	try:
		yield db

	finally:
		client.drop_database(database_name)
		client.close()


def legacy_payload():
	return {
		'application': 'oxkat',
		'operation': 'stage_test',
		'parameters': {
			'stage': 'TEST'
		},
		'input_runs': [],
		'input_artifacts': []
	}


def request_payload():
	return {
		'stage': 'TEST',
		'node_id': 'stage_test',
		'parameters': {}
	}


def create_direct(key, fingerprint=None):
	if fingerprint is None:
		fingerprint = idempotency.fingerprint(
			request_payload()
		)

	return manager.create_run(
		'alice',
		'p1',
		'stage_test',
		legacy_payload(),
		idempotency_key=key,
		request_fingerprint=fingerprint
	)


def test_unique_idempotency_index_exists(mongo_context):
	indexes = mongo_context.pipeline_runs.index_information()

	assert 'pipeline_run_idempotency_v1' in indexes

	index = indexes['pipeline_run_idempotency_v1']

	assert index['unique'] is True
	assert index['key'] == [
		('owner', 1),
		('pipeline_id', 1),
		('idempotency_key', 1)
	]


def test_concurrent_identical_registration(
	monkeypatch,
	mongo_context
):
	"""Force both requests past validation before their inserts."""

	barrier = threading.Barrier(2)

	def synchronized_binding(*args, **kwargs):
		barrier.wait(timeout=15)
		return []

	monkeypatch.setattr(
		binding,
		'bind_inputs',
		synchronized_binding
	)

	key = 'concurrent:001'

	with ThreadPoolExecutor(max_workers=2) as executor:
		futures = [
			executor.submit(create_direct, key)
			for _ in range(2)
		]

		results = [
			future.result(timeout=30)
			for future in futures
		]

	query = {
		'owner': 'alice',
		'pipeline_id': 'p1',
		'idempotency_key': key
	}

	assert mongo_context.pipeline_runs.count_documents(query) == 1

	assert len({
		result['run_id']
		for result in results
	}) == 1

	assert sorted(
		result['idempotency_replayed']
		for result in results
	) == [False, True]


def test_same_key_different_fingerprint(mongo_context):
	key = 'conflict:001'

	original = create_direct(key)

	different_request = request_payload()
	different_request['parameters']['iterations'] = 5

	different_fingerprint = idempotency.fingerprint(
		different_request
	)

	with pytest.raises(manager.PipelineError) as exc:
		create_direct(key, different_fingerprint)

	assert exc.value.status == 409

	assert mongo_context.pipeline_runs.count_documents({
		'owner': 'alice',
		'pipeline_id': 'p1',
		'idempotency_key': key
	}) == 1

	stored = mongo_context.pipeline_runs.find_one({
		'idempotency_key': key
	})

	assert stored['run_id'] == original['run_id']


class InsertProxy:
	"""Simulate lost MongoDB acknowledgment at the insertion boundary."""

	def __init__(self, collection, commit_first):
		self.collection = collection
		self.commit_first = commit_first

	def insert_one(self, document):
		if self.commit_first:
			self.collection.insert_one(document)

		raise AutoReconnect(
			'Simulated lost MongoDB acknowledgment'
		)

	def __getattr__(self, name):
		return getattr(self.collection, name)


def test_lost_acknowledgment_after_commit(
	monkeypatch,
	mongo_context
):
	"""A committed insertion must be recovered by its unique key."""

	runs = InsertProxy(
		mongo_context.pipeline_runs,
		commit_first=True
	)

	monkeypatch.setattr(
		manager,
		'collections',
		lambda: (
			mongo_context.pipelines,
			runs,
			mongo_context.pipeline_counters
		)
	)

	result = create_direct('uncertain:committed')

	assert result['idempotency_replayed'] is True

	assert mongo_context.pipeline_runs.count_documents({
		'idempotency_key': 'uncertain:committed'
	}) == 1

	stored = mongo_context.pipeline_runs.find_one({
		'idempotency_key': 'uncertain:committed'
	})

	assert result['run_id'] == stored['run_id']


def test_failure_before_commit_allows_safe_retry(
	monkeypatch,
	mongo_context
):
	"""No run inserted: a later request can register the same key."""

	runs = InsertProxy(
		mongo_context.pipeline_runs,
		commit_first=False
	)

	monkeypatch.setattr(
		manager,
		'collections',
		lambda: (
			mongo_context.pipelines,
			runs,
			mongo_context.pipeline_counters
		)
	)

	key = 'uncertain:not-committed'

	with pytest.raises(manager.PipelineError) as exc:
		create_direct(key)

	assert exc.value.status == 503

	assert mongo_context.pipeline_runs.count_documents({
		'idempotency_key': key
	}) == 0

	# Restore the actual collection, simulating a recovered connection.
	monkeypatch.setattr(
		manager,
		'collections',
		lambda: (
			mongo_context.pipelines,
			mongo_context.pipeline_runs,
			mongo_context.pipeline_counters
		)
	)

	result = create_direct(key)

	assert result['idempotency_replayed'] is False

	assert mongo_context.pipeline_runs.count_documents({
		'idempotency_key': key
	}) == 1


def test_single_run_replay_skips_artifact_binding(
	monkeypatch,
	mongo_context
):
	"""Replay must not redo scientific input validation or binding."""

	app = Flask(__name__)

	app.config['PIPELINE_V2_APPLICATIONS'] = {
		'oxkat': {
			'parameters': {
				'stage': ['TEST']
			},
			'input_options_by_stage': {
				'TEST': {}
			}
		}
	}

	payload = {
		'stage': 'TEST',
		'node_id': 'stage_test',
		'idempotency_key': 'single:replay:001'
	}

	with app.app_context():
		first = manager.create_run_simple(
			'alice',
			'p1',
			payload
		)

		def forbidden_binding(*args, **kwargs):
			raise AssertionError(
				'Replay unexpectedly attempted artifact binding'
			)

		monkeypatch.setattr(
			binding,
			'bind_inputs',
			forbidden_binding
		)

		second = manager.create_run_simple(
			'alice',
			'p1',
			payload
		)

	assert first['idempotency_replayed'] is False
	assert second['idempotency_replayed'] is True
	assert first['run_id'] == second['run_id']

	assert mongo_context.pipeline_runs.count_documents({
		'idempotency_key': 'single:replay:001'
	}) == 1

