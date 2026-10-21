"""Regression tests for Slurm accounting monitoring fallback."""

from types import SimpleNamespace

import pytest

from caesar_rest import job_monitor


def make_job(state='RUNNING'):
	return {
		'job_id': 'j1',
		'pid': 18500,
		'state': state,
		'elapsed_time': 30
	}


def accounting_result(state='SUCCESS'):
	return {
		'pid': '18500',
		'state': state,
		'status': 'Recovered from Slurm accounting',
		'exit_code': 0 if state == 'SUCCESS' else 1,
		'elapsed_time': 156
	}


@pytest.mark.parametrize(
	'accounting,expected',
	[
		(accounting_result('SUCCESS'), 'SUCCESS'),
		(accounting_result('FAILURE'), 'FAILURE'),
		(accounting_result('CANCELED'), 'CANCELED'),
		(accounting_result('TIMED-OUT'), 'TIMED-OUT'),
		(None, 'CLEARED')
	]
)
def test_missing_running_job_recovery(
		monkeypatch, accounting, expected):

	lookups = []

	def lookup(pid):
		lookups.append(pid)
		return accounting

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_accounting_job_status=lookup
		)
	)

	result = job_monitor.recover_missing_slurm_job(
		make_job()
	)

	assert result['state'] == expected
	assert lookups == ['18500']


def test_accounting_exception_preserves_cleared(monkeypatch):
	def failing_lookup(pid):
		raise RuntimeError('Accounting unavailable')

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_accounting_job_status=failing_lookup
		)
	)

	result = job_monitor.recover_missing_slurm_job(
		make_job()
	)

	assert result['state'] == 'CLEARED'
	assert result['exit_code'] == -1


def test_pending_job_does_not_use_accounting(monkeypatch):
	calls = []

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_accounting_job_status=lambda pid: calls.append(pid)
		)
	)

	assert job_monitor.recover_missing_slurm_job(
		make_job('PENDING')
	) is None

	assert calls == []


def test_mismatched_accounting_identity_uses_cleared(monkeypatch):
	invalid = accounting_result()
	invalid['pid'] = '99999'

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_accounting_job_status=lambda pid: invalid
		)
	)

	result = job_monitor.recover_missing_slurm_job(
		make_job()
	)

	assert result['state'] == 'CLEARED'


@pytest.mark.parametrize(
	'controller_response,accounting_state,expected',
	[
		({}, 'SUCCESS', 'SUCCESS'),
		({}, None, 'CLEARED'),
		({'99999': accounting_result()}, 'FAILURE', 'FAILURE'),
		({'18500': accounting_result('SUCCESS')}, None, 'SUCCESS')
	]
)
def test_batch_monitoring_accounting_integration(
		monkeypatch,
		controller_response,
		accounting_state,
		expected):

	lookups = []
	updates = []

	def lookup(pid):
		lookups.append(pid)
		if accounting_state is None:
			return None
		return accounting_result(accounting_state)

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_statuses=lambda pids: controller_response,
			get_accounting_job_status=lookup
		)
	)

	monkeypatch.setattr(
		job_monitor,
		'update_slurm_job',
		lambda job, result, collection: (
			updates.append(result) or 0
		)
	)

	assert job_monitor.monitor_slurm_jobs(
		[make_job()],
		SimpleNamespace()
	) == 0

	assert len(updates) == 1
	assert updates[0]['state'] == expected

	if '18500' in controller_response:
		assert lookups == []
	else:
		assert lookups == ['18500']


def test_controller_failure_does_not_query_accounting(monkeypatch):
	lookups = []
	updates = []

	monkeypatch.setattr(
		job_monitor,
		'jobmgr_slurm',
		SimpleNamespace(
			get_job_statuses=lambda pids: None,
			get_accounting_job_status=lambda pid: lookups.append(pid)
		)
	)

	monkeypatch.setattr(
		job_monitor,
		'update_slurm_job',
		lambda *args: updates.append(args) or 0
	)

	assert job_monitor.monitor_slurm_jobs(
		[make_job()],
		SimpleNamespace()
	) == -1

	assert lookups == []
	assert updates == []
