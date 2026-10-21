"""Tests for single-job Slurm monitoring delegation."""

from types import SimpleNamespace

import pytest

from caesar_rest import job_monitor


def make_job():
	return {
		'job_id': 'j1',
		'pid': 18500,
		'state': 'RUNNING',
		'elapsed_time': 30
	}


def make_result(state='SUCCESS'):
	return {
		'pid': '18500',
		'state': state,
		'status': 'Slurm test result',
		'exit_code': 0,
		'elapsed_time': 156
	}


def test_single_job_delegates_to_batch_monitor(monkeypatch):
	job = make_job()
	collection = SimpleNamespace()
	calls = []

	def fake_batch(jobs, coll):
		calls.append((jobs, coll))
		return 0

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace()
	)
	monkeypatch.setattr(
		job_monitor,
		'monitor_slurm_jobs',
		fake_batch
	)

	assert job_monitor.monitor_slurm_job(job, collection) == 0
	assert len(calls) == 1
	assert calls[0][0] == [job]
	assert calls[0][1] is collection


def test_single_job_propagates_failure(monkeypatch):
	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace()
	)
	monkeypatch.setattr(
		job_monitor,
		'monitor_slurm_jobs',
		lambda jobs, collection: -1
	)

	assert job_monitor.monitor_slurm_job(
		make_job(), SimpleNamespace()
	) == -1


@pytest.mark.parametrize(
	'job,collection',
	[
		(None, object()),
		({}, object()),
		({'job_id': 'j1', 'pid': ''}, object()),
		(make_job(), None)
	]
)
def test_single_job_rejects_invalid_inputs(
		monkeypatch, job, collection):

	calls = []

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace()
	)
	monkeypatch.setattr(
		job_monitor,
		'monitor_slurm_jobs',
		lambda jobs, coll: calls.append((jobs, coll))
	)

	assert job_monitor.monitor_slurm_job(job, collection) == -1
	assert calls == []


def test_single_job_recovers_from_accounting(monkeypatch):
	job = make_job()
	updates = []
	lookups = []

	def accounting_lookup(pid):
		lookups.append(pid)
		return make_result()

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_statuses=lambda pids: {},
			get_accounting_job_status=accounting_lookup
		)
	)

	monkeypatch.setattr(
		job_monitor,
		'update_slurm_job',
		lambda job_obj, result, collection: (
			updates.append(result) or 0
		)
	)

	assert job_monitor.monitor_slurm_job(
		job, SimpleNamespace()
	) == 0

	assert lookups == ['18500']
	assert updates[0]['state'] == 'SUCCESS'


def test_controller_failure_does_not_recover(monkeypatch):
	accounting_calls = []
	updates = []

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_statuses=lambda pids: None,
			get_accounting_job_status=lambda pid: (
				accounting_calls.append(pid)
			)
		)
	)

	monkeypatch.setattr(
		job_monitor,
		'update_slurm_job',
		lambda *args: updates.append(args) or 0
	)

	assert job_monitor.monitor_slurm_job(
		make_job(), SimpleNamespace()
	) == -1

	assert accounting_calls == []
	assert updates == []
