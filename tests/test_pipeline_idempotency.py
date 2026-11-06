
"""Unit tests for Pipeline V2 registration idempotency primitives."""

import pytest

from caesar_rest.pipeline import idempotency
from caesar_rest.pipeline import manager


class FakeRuns:
	def __init__(self, document=None):
		self.document = document
		self.queries = []

	def find_one(self, query):
		self.queries.append(dict(query))

		if self.document is None:
			return None

		if all(
			self.document.get(key) == value
			for key, value in query.items()
		):
			return dict(self.document)

		return None


def request_payload():
	return {
		'stage': 'PROCESS',
		'node_id': 'process_f1',
		'parameters': {
			'target': 'TARGET_A',
			'iterations': 3
		},
		'inputs': {
			'data': {
				'run_id': 'source1',
				'artifact': 'output',
				'artifact_index': 0
			}
		}
	}


def existing_document(payload=None):
	if payload is None:
		payload = request_payload()

	return {
		'_id': 'mongo-internal-id',
		'owner': 'alice',
		'pipeline_id': 'p1',
		'run_id': 'run1',
		'node_id': 'process_f1',
		'status': 'PLANNED',
		'idempotency_key': 'request-001',
		'request_fingerprint': idempotency.fingerprint(payload)
	}


def test_valid_idempotency_keys():
	for key in (
		'request-001',
		'maasai:workflow:1',
		'run_123',
		'abc.def'
	):
		assert idempotency.validate_key(key) == key


def test_invalid_idempotency_keys():
	for key in (
		'',
		'bad key',
		'/unsafe/key',
		'bad@key',
		'a' * 129,
		None,
		123
	):
		with pytest.raises(manager.PipelineError) as exc:
			idempotency.validate_key(key)

		assert exc.value.status == 400


def test_fingerprint_ignores_dictionary_order():
	first = request_payload()

	second = {
		'inputs': {
			'data': {
				'artifact_index': 0,
				'artifact': 'output',
				'run_id': 'source1'
			}
		},
		'parameters': {
			'iterations': 3,
			'target': 'TARGET_A'
		},
		'node_id': 'process_f1',
		'stage': 'PROCESS'
	}

	assert (
		idempotency.fingerprint(first)
		== idempotency.fingerprint(second)
	)


def test_fingerprint_detects_changed_request():
	first = request_payload()
	second = request_payload()

	second['parameters']['iterations'] = 4

	assert (
		idempotency.fingerprint(first)
		!= idempotency.fingerprint(second)
	)


def test_missing_registration_returns_none():
	runs = FakeRuns()

	result = idempotency.find_existing(
		runs,
		'alice',
		'p1',
		'request-001',
		idempotency.fingerprint(request_payload())
	)

	assert result is None
	assert runs.queries == [{
		'owner': 'alice',
		'pipeline_id': 'p1',
		'idempotency_key': 'request-001'
	}]


def test_matching_replay_returns_original_run():
	runs = FakeRuns(existing_document())

	result = idempotency.find_existing(
		runs,
		'alice',
		'p1',
		'request-001',
		idempotency.fingerprint(request_payload())
	)

	assert result['run_id'] == 'run1'
	assert result['status'] == 'PLANNED'
	assert 'owner' not in result
	assert '_id' not in result


def test_same_key_different_payload_is_conflict():
	runs = FakeRuns(existing_document())

	changed = request_payload()
	changed['parameters']['iterations'] = 99

	with pytest.raises(manager.PipelineError) as exc:
		idempotency.find_existing(
			runs,
			'alice',
			'p1',
			'request-001',
			idempotency.fingerprint(changed)
		)

	assert exc.value.status == 409


def test_registration_is_owner_scoped():
	runs = FakeRuns(existing_document())

	result = idempotency.find_existing(
		runs,
		'bob',
		'p1',
		'request-001',
		idempotency.fingerprint(request_payload())
	)

	assert result is None


def test_non_json_payload_rejected():
	with pytest.raises(manager.PipelineError) as exc:
		idempotency.fingerprint({
			'object': object()
		})

	assert exc.value.status == 400

