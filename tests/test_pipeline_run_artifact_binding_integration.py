"""Integration of frozen input artifact bindings into create_run()."""
from types import SimpleNamespace

import pytest

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import binding


class FakeRuns:
	def __init__(self):
		self.created = []

	def find_one(self, query):
		if query.get('run_id') == 'source-run' and query.get('owner') == 'alice' and query.get('pipeline_id') == 'p1':
			return {'run_id': 'source-run', 'status': 'COMPLETED'}
		return None

	def insert_one(self, document):
		self.created.append(dict(document))


class FakeCounters:
	def __init__(self):
		self.calls = 0

	def find_one_and_update(self, *args, **kwargs):
		self.calls += 1
		return {'sequence': self.calls}


def _setup(monkeypatch, bind_function):
	runs = FakeRuns()
	counters = FakeCounters()
	monkeypatch.setattr(manager, 'get_pipeline', lambda owner, pipeline_id: {'owner': owner, 'pipeline_id': pipeline_id})
	monkeypatch.setattr(manager, 'collections', lambda: (None, runs, counters))
	monkeypatch.setattr(manager, 'mongo', SimpleNamespace(db=object()))
	monkeypatch.setattr(binding, 'bind_inputs', bind_function)
	return runs, counters


def _payload(include_parent=True):
	return {
		'application': 'oxkat',
		'operation': 'FLAG',
		'parameters': {},
		'input_runs': ['source-run'] if include_parent else [],
		'input_artifacts': [{
			'input_name': 'calibrated_ms',
			'source_run_id': 'source-run',
			'artifact_index': 0
		}]
	}


def test_create_run_persists_frozen_binding_before_allocating_sequence(monkeypatch):
	calls = []
	frozen = {
		'input_name': 'calibrated_ms',
		'source_pipeline_id': 'p1',
		'source_node_id': 'calibration',
		'source_run_id': 'source-run',
		'artifact_index': 0,
		'artifact_name': 'calibrated_ms',
		'artifact_kind': 'directory',
		'size_bytes': 100,
		'manifest_sha256': 'a' * 64
	}

	def fake_bind(db, owner, pipeline_id, requests, retention_root, **kwargs):
		assert owner == 'alice' and pipeline_id == 'p1'
		assert retention_root == '/retained'
		assert requests[0]['source_run_id'] == 'source-run'
		assert counters.calls == 0
		calls.append(True)
		return [dict(frozen)]

	runs, counters = _setup(monkeypatch, fake_bind)
	result = manager.create_run('alice', 'p1', 'imaging', _payload(), retention_root='/retained')
	assert calls == [True]
	assert counters.calls == 1
	assert len(runs.created) == 1
	assert result['status'] == 'PLANNED'
	assert result['run_name'] == 'run001'
	assert result['input_artifacts'] == [frozen]
	assert runs.created[0]['input_artifacts'] == [frozen]
	assert result['input_runs'] == ['source-run']
	assert '_id' not in result


def test_failed_binding_does_not_allocate_sequence_or_create_run(monkeypatch):
	def reject(*args, **kwargs):
		raise manager.PipelineError('Upstream artifact is not retained', 409)

	runs, counters = _setup(monkeypatch, reject)
	with pytest.raises(manager.PipelineError) as exc:
		manager.create_run('alice', 'p1', 'imaging', _payload(), retention_root='/retained')
	assert exc.value.status == 409
	assert counters.calls == 0
	assert runs.created == []


def test_missing_parent_reference_does_not_allocate_sequence(monkeypatch):
	def fake_bind(*args, **kwargs):
		return [{'source_run_id': 'source-run'}]

	runs, counters = _setup(monkeypatch, fake_bind)
	with pytest.raises(manager.PipelineError, match='input_runs'):
		manager.create_run('alice', 'p1', 'imaging', _payload(include_parent=False))
	assert counters.calls == 0
	assert runs.created == []
	
def test_readiness_for_planned_run():
	run = {
		'status': 'PLANNED',
		'artifacts': []
	}

	result = manager.run_readiness(run)

	assert result['artifacts_status'] == 'NOT_REGISTERED'
	assert result['readiness'] == {
		'can_select': False,
		'can_consume': False
	}


def test_readiness_for_completed_run_without_artifacts():
	run = {
		'status': 'COMPLETED',
		'artifacts': []
	}

	result = manager.run_readiness(run)

	assert result['artifacts_status'] == 'NOT_REGISTERED'
	assert result['readiness'] == {
		'can_select': True,
		'can_consume': False
	}


def test_readiness_for_registered_run_without_retention():
	run = {
		'status': 'COMPLETED',
		'artifacts_registered_at': 'now',
		'artifacts': [{'name': 'output'}]
	}

	result = manager.run_readiness(run)

	assert result['artifacts_status'] == 'REGISTERED'
	assert result['readiness'] == {
		'can_select': True,
		'can_consume': False
	}


def test_readiness_for_pending_retention():
	run = {
		'status': 'COMPLETED',
		'artifacts_registered_at': 'now',
		'artifacts': [{'name': 'output'}],
		'retention_status': 'PENDING'
	}

	result = manager.run_readiness(run)

	assert result['artifacts_status'] == 'PENDING'
	assert result['readiness']['can_consume'] is False


def test_readiness_for_completed_retained_run():
	run = {
		'status': 'COMPLETED',
		'artifacts_registered_at': 'now',
		'artifacts': [{'name': 'output'}],
		'retained_artifacts': [
			{'index': 0, 'name': 'output'}
		],
		'retention_status': 'READY'
	}

	result = manager.run_readiness(run)

	assert result['artifacts_status'] == 'READY'
	assert result['readiness'] == {
		'can_select': True,
		'can_consume': True
	}


def test_readiness_rejects_incomplete_retention_metadata():
	run = {
		'status': 'COMPLETED',
		'artifacts_registered_at': 'now',
		'artifacts': [
			{'name': 'output1'},
			{'name': 'output2'}
		],
		'retained_artifacts': [
			{'index': 0, 'name': 'output1'}
		]
	}

	result = manager.run_readiness(run)

	assert result['artifacts_status'] != 'READY'
	assert result['readiness']['can_consume'] is False


def test_failed_run_cannot_be_selected_or_consumed():
	run = {
		'status': 'FAILED',
		'artifacts_registered_at': 'now',
		'artifacts': [{'name': 'output'}],
		'retained_artifacts': [
			{'index': 0, 'name': 'output'}
		]
	}

	result = manager.run_readiness(run)

	assert result['artifacts_status'] != 'READY'
	assert result['readiness']['can_select'] is False
	assert result['readiness']['can_consume'] is False
	
		
	
