"""Regression tests for monitored pipeline job synchronization."""

from types import SimpleNamespace

import pytest

from caesar_rest.pipeline import status


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


def test_completed_transition_registers_artifacts(monkeypatch):
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


def test_repeated_completion_retries_registration(monkeypatch):
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


@pytest.mark.parametrize(
	'existing_run',
	[
		None,
		{'status': 'FAILED'},
		{'status': 'CANCELLED'}
	]
)
def test_rejected_update_does_not_register_artifacts(
		monkeypatch, existing_run):

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


def test_running_transition_does_not_register_artifacts(monkeypatch):
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
