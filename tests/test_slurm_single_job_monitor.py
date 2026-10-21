"""Regression tests for the single-job Slurm monitoring path."""

from types import SimpleNamespace

import pytest

from caesar_rest import job_monitor


def make_job():
	return {
		'job_id': 'test-job',
		'pid': 18500,
		'state': 'RUNNING',
		'elapsed_time': 30
	}


def make_result(state='RUNNING'):
	return {
		'state': state,
		'status': 'Slurm test response',
		'exit_code': 0,
		'elapsed_time': 120
	}


@pytest.mark.parametrize(
	'state',
	['RUNNING', 'SUCCESS', 'FAILURE', 'CANCELED', 'TIMED-OUT']
)
def test_single_job_uses_shared_updater(monkeypatch, state):
	job = make_job()
	result = make_result(state)
	collection = SimpleNamespace()

	calls = []

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_status=lambda pid: result
		)
	)

	def fake_update(job_obj, response, job_collection):
		calls.append((job_obj, response, job_collection))
		return 0

	monkeypatch.setattr(
		job_monitor,
		'update_slurm_job',
		fake_update
	)

	assert job_monitor.monitor_slurm_job(job, collection) == 0

	assert len(calls) == 1
	assert calls[0][0] is job
	assert calls[0][1] is result
	assert calls[0][2] is collection


def test_single_job_missing_status_does_not_update(monkeypatch):
	calls = []

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_status=lambda pid: None
		)
	)

	monkeypatch.setattr(
		job_monitor,
		'update_slurm_job',
		lambda *args: calls.append(args)
	)

	assert job_monitor.monitor_slurm_job(
		make_job(),
		SimpleNamespace()
	) == -1

	assert calls == []


def test_single_job_controller_exception_does_not_update(monkeypatch):
	calls = []

	def failed_request(pid):
		raise RuntimeError('Slurm REST unavailable')

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_status=failed_request
		)
	)

	monkeypatch.setattr(
		job_monitor,
		'update_slurm_job',
		lambda *args: calls.append(args)
	)

	assert job_monitor.monitor_slurm_job(
		make_job(),
		SimpleNamespace()
	) == -1

	assert calls == []


def test_single_job_propagates_updater_failure(monkeypatch):
	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_status=lambda pid: make_result('SUCCESS')
		)
	)

	monkeypatch.setattr(
		job_monitor,
		'update_slurm_job',
		lambda *args: -1
	)

	assert job_monitor.monitor_slurm_job(
		make_job(),
		SimpleNamespace()
	) == -1


def test_single_job_rejects_invalid_inputs(monkeypatch):
	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_status=lambda pid: make_result()
		)
	)

	assert job_monitor.monitor_slurm_job(
		None, SimpleNamespace()
	) == -1

	assert job_monitor.monitor_slurm_job(
		make_job(), None
	) == -1

	job = make_job()
	job['pid'] = ''

	assert job_monitor.monitor_slurm_job(
		job, SimpleNamespace()
	) == -1
