"""Regression tests for guarded Slurm monitoring updates."""

from types import SimpleNamespace

import pytest

from caesar_rest import job_monitor


def make_job():
	return {
		'job_id': 'j1',
		'pid': 18500,
		'state': 'RUNNING'
	}


def make_result(state, elapsed_time=156):
	return {
		'state': state,
		'status': 'Test observation',
		'exit_code': 0 if state == 'SUCCESS' else -1,
		'elapsed_time': elapsed_time
	}


class FakeCollection:
	def __init__(self, current_state, current_pid=18500):
		self.current_state = current_state
		self.current_pid = current_pid
		self.elapsed_time = 30
		self.query = None
		self.update = None

	def update_one(self, query, update, upsert=False):
		self.query = query
		self.update = update

		allowed = query['state']
		if isinstance(allowed, dict):
			state_matches = self.current_state in allowed['$in']
		else:
			state_matches = self.current_state == allowed

		matched = (
			query['job_id'] == 'j1'
			and query['pid'] == self.current_pid
			and state_matches
		)

		if matched:
			self.current_state = update['$set']['state']
			self.elapsed_time = update['$set']['elapsed_time']

		return SimpleNamespace(
			matched_count=1 if matched else 0,
			modified_count=1 if matched else 0
		)


@pytest.mark.parametrize(
	'current_state,observed_state,expected_state,accepted',
	[
		('PENDING', 'RUNNING', 'RUNNING', True),
		('RUNNING', 'RUNNING', 'RUNNING', True),
		('RUNNING', 'SUCCESS', 'SUCCESS', True),
		('RUNNING', 'FAILURE', 'FAILURE', True),
		('RUNNING', 'CANCELED', 'CANCELED', True),
		('RUNNING', 'CLEARED', 'CLEARED', True),
		('PENDING', 'CLEARED', 'PENDING', False),
		('SUCCESS', 'RUNNING', 'SUCCESS', False),
		('FAILURE', 'SUCCESS', 'FAILURE', False),
		('CANCELED', 'RUNNING', 'CANCELED', False),
		('TIMED-OUT', 'SUCCESS', 'TIMED-OUT', False),
		('CLEARED', 'SUCCESS', 'CLEARED', False)
	]
)
def test_atomic_job_transition(
		monkeypatch, current_state, observed_state,
		expected_state, accepted):

	collection = FakeCollection(current_state)
	sync_calls = []

	monkeypatch.setattr(
		job_monitor,
		'safe_sync_monitored_pipeline_job',
		lambda *args, **kwargs: sync_calls.append(
			(args, kwargs)
		)
	)

	assert job_monitor.update_slurm_job(
		make_job(),
		make_result(observed_state),
		collection
	) == 0

	assert collection.current_state == expected_state
	assert len(sync_calls) == (1 if accepted else 0)


def test_running_refresh_updates_elapsed_time(monkeypatch):
	collection = FakeCollection('RUNNING')

	monkeypatch.setattr(
		job_monitor,
		'safe_sync_monitored_pipeline_job',
		lambda *args, **kwargs: None
	)

	assert job_monitor.update_slurm_job(
		make_job(),
		make_result('RUNNING', elapsed_time=240),
		collection
	) == 0

	assert collection.current_state == 'RUNNING'
	assert collection.elapsed_time == 240


def test_scheduler_pid_mismatch_rejects_update(monkeypatch):
	collection = FakeCollection(
		current_state='RUNNING',
		current_pid=99999
	)
	sync_calls = []

	monkeypatch.setattr(
		job_monitor,
		'safe_sync_monitored_pipeline_job',
		lambda *args, **kwargs: sync_calls.append(args)
	)

	assert job_monitor.update_slurm_job(
		make_job(),
		make_result('SUCCESS'),
		collection
	) == 0

	assert collection.current_state == 'RUNNING'
	assert sync_calls == []


def test_cleared_requires_running_state(monkeypatch):
	collection = FakeCollection('PENDING')

	monkeypatch.setattr(
		job_monitor,
		'safe_sync_monitored_pipeline_job',
		lambda *args, **kwargs: None
	)

	assert job_monitor.update_slurm_job(
		make_job(),
		make_result('CLEARED'),
		collection
	) == 0

	assert collection.query['state'] == 'RUNNING'
	assert collection.current_state == 'PENDING'
