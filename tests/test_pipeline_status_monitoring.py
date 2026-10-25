"""Regression tests for monitored pipeline job synchronization."""

from types import SimpleNamespace

import pytest

from caesar_rest.pipeline import status

# - Preserve the actual function for direct retention tests.
_original_safe_retain_artifacts = status.safe_retain_artifacts


@pytest.fixture
def retention_calls(monkeypatch):
	"""Intercept automatic retention during synchronization tests."""
	calls = []

	monkeypatch.setattr(
		status,
		'safe_retain_artifacts',
		lambda *args: calls.append(args) or True
	)

	return calls

class FakeRuns:
	def __init__(self, modified_count, existing_run=None):
		self.modified_count = modified_count
		self.existing_run = existing_run
		self.updated = None
		self.looked_up = None

	def update_one(self, query, update):
		self.updated = (query, update)
		return SimpleNamespace(modified_count=self.modified_count)
	
	def find_one(self, query):
		self.looked_up = query

		if self.existing_run is None:
			return None

		if self.existing_run.get('status') != query.get('status'):
			return None

		return self.existing_run


class FakeDB:
	def __init__(self, runs):
		self.pipeline_runs = runs


def job():
	return {
		'_pipeline_sync_owner': 'alice',
		'pipeline_id': 'p1',
		'run_id': 'r1',
		'job_id': 'j1'
	}


def test_completed_transition_registers_artifacts(monkeypatch, retention_calls):
	runs = FakeRuns(modified_count=1)
	db = FakeDB(runs)
	calls = []

	monkeypatch.setattr(
		status,
		'safe_register_artifacts',
		lambda *args: calls.append(args)
	)

	assert status.synchronize_monitored_job(
		db, job(), 'SUCCESS', 0
	) is True

	assert len(calls) == 1
	assert runs.updated[1]['$set']['status'] == 'COMPLETED'
	# - Retention must not run inside the job monitoring callback.
	assert retention_calls == []


def test_repeated_completion_retries_registration(monkeypatch, retention_calls):
	runs = FakeRuns(
		modified_count=0,
		existing_run={'status': 'COMPLETED'}
	)
	db = FakeDB(runs)
	calls = []

	monkeypatch.setattr(
		status,
		'safe_register_artifacts',
		lambda *args: calls.append(args)
	)

	assert status.synchronize_monitored_job(
		db, job(), 'SUCCESS', 0
	) is False

	assert len(calls) == 1
	assert runs.looked_up == {
		'owner': 'alice',
		'pipeline_id': 'p1',
		'run_id': 'r1',
		'job_id': 'j1',
		'status': 'COMPLETED'
	}
	# - Repeated completion may retry registration, but never copying.
	assert retention_calls == []


@pytest.mark.parametrize(
	'existing_run',
	[
		None,
		{'status': 'FAILED'},
		{'status': 'CANCELLED'}
	]
)
def test_rejected_update_does_not_register_artifacts(
		monkeypatch, existing_run, retention_calls):

	runs = FakeRuns(
		modified_count=0,
		existing_run=existing_run
	)
	db = FakeDB(runs)
	calls = []

	monkeypatch.setattr(
		status,
		'safe_register_artifacts',
		lambda *args: calls.append(args)
	)

	assert status.synchronize_monitored_job(
		db, job(), 'SUCCESS', 0
	) is False

	assert calls == []
	assert retention_calls == []


def test_running_transition_does_not_register_artifacts(monkeypatch, retention_calls):
	runs = FakeRuns(modified_count=1)
	db = FakeDB(runs)
	calls = []

	monkeypatch.setattr(
		status,
		'safe_register_artifacts',
		lambda *args: calls.append(args)
	)

	assert status.synchronize_monitored_job(
		db, job(), 'RUNNING'
	) is True

	assert runs.updated[1]['$set']['status'] == 'RUNNING'
	assert calls == []
	assert retention_calls == []	
	
def test_running_observation_only_updates_submitted_run(monkeypatch, retention_calls):
	runs = FakeRuns(modified_count=0)
	db = FakeDB(runs)
	calls = []

	monkeypatch.setattr(
		status,
		'safe_register_artifacts',
		lambda *args: calls.append(args)
	)

	assert status.synchronize_monitored_job(
		db, job(), 'RUNNING'
	) is False

	assert runs.updated[0]['status'] == {
		'$in': ['SUBMITTED']
	}
	assert calls == []
	assert retention_calls == []
		
def test_standalone_monitor_uses_explicit_retention_config(monkeypatch):
	runs = FakeRuns(
		modified_count=0,
		existing_run={
			'status': 'COMPLETED',
			'node_id': 'getinfo',
			'artifacts_registered_at': 'now',
			'artifacts': [{'name': 'project_info'}]
		}
	)
	db = FakeDB(runs)
	calls = []

	config = {
		'PIPELINE_ARTIFACT_RETENTION_ROOT': '/tmp/pipeline-artifacts',
		'PIPELINE_ARTIFACT_RETENTION_MAX_FILE_BYTES': 1024,
		'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES': 2048,
		'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES': 100,
		'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH': 8
	}

	monkeypatch.setattr(
		status,
		'MONITOR_RETENTION_CONFIG',
		config
	)

	monkeypatch.setattr(
		status.pipeline_artifact_retention,
		'promote_run',
		lambda *args: calls.append(args)
	)

	assert _original_safe_retain_artifacts(
		db, 'alice', 'p1', 'r1', 'j1'
	) is True

	assert len(calls) == 1
	assert calls[0][1:6] == (
		'alice',
		'p1',
		'getinfo',
		'r1',
		'/tmp/pipeline-artifacts'
	)
	assert calls[0][6:] == (1024, 2048, 100, 8)


def test_retention_without_config_fails_safely(monkeypatch):
	runs = FakeRuns(
		modified_count=0,
		existing_run={
			'status': 'COMPLETED',
			'node_id': 'getinfo',
			'artifacts_registered_at': 'now',
			'artifacts': [{'name': 'project_info'}]
		}
	)

	monkeypatch.setattr(
		status,
		'MONITOR_RETENTION_CONFIG',
		{}
	)

	assert _original_safe_retain_artifacts(
		FakeDB(runs), 'alice', 'p1', 'r1', 'j1'
	) is False


def test_retention_failure_does_not_change_job_completion(
		monkeypatch, retention_calls):

	runs = FakeRuns(modified_count=1)
	db = FakeDB(runs)

	monkeypatch.setattr(
		status,
		'safe_register_artifacts',
		lambda *args: True
	)

	monkeypatch.setattr(
		status,
		'safe_retain_artifacts',
		lambda *args: False
	)

	assert status.synchronize_monitored_job(
		db, job(), 'SUCCESS', 0
	) is True

	assert runs.updated[1]['$set']['status'] == 'COMPLETED'		
		

def test_completed_transition_never_copies_artifacts(
		monkeypatch, retention_calls):
	"""Job monitoring must not invoke synchronous artifact retention."""

	runs = FakeRuns(modified_count=1)
	db = FakeDB(runs)
	registration_calls = []

	monkeypatch.setattr(
		status,
		'safe_register_artifacts',
		lambda *args: registration_calls.append(args)
	)

	assert status.synchronize_monitored_job(
		db, job(), 'SUCCESS', 0
	) is True

	assert len(registration_calls) == 1
	assert retention_calls == []
		
