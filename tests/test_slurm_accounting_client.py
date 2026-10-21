"""Regression tests for Slurm REST accounting lookup."""

from types import SimpleNamespace

import pytest
import requests

from caesar_rest import slurm_client


def accounting_job(
		job_id=18500,
		state='COMPLETED',
		exit_code=0,
		exit_status='SUCCESS'):

	return {
		'job_id': job_id,
		'state': {
			'current': state,
			'previous': 'None'
		},
		'exit_code': {
			'status': exit_status,
			'return_code': exit_code
		},
		'derived_exit_code': {
			'status': exit_status,
			'return_code': exit_code
		},
		'time': {
			'elapsed': 156
		}
	}


def make_client(monkeypatch, payload, status_code=200):
	client = slurm_client.SlurmJobManager()
	client.username = 'caesar'
	client.token = 'test-token'
	client.cluster_url = (
		'http://127.0.0.1:6820/slurm/v0.0.36'
	)

	monkeypatch.setattr(
		client,
		'is_token_active',
		lambda: True
	)

	calls = []

	def fake_get(url, headers, timeout):
		calls.append({
			'url': url,
			'headers': headers,
			'timeout': timeout
		})

		def raise_for_status():
			if status_code >= 400:
				raise requests.HTTPError('HTTP error')

		return SimpleNamespace(
			json=lambda: payload,
			raise_for_status=raise_for_status
		)

	monkeypatch.setattr(
		slurm_client.requests,
		'get',
		fake_get
	)

	return client, calls


def test_completed_accounting_job(monkeypatch):
	client, calls = make_client(
		monkeypatch,
		{
			'errors': [],
			'jobs': [accounting_job()]
		}
	)

	result = client.get_accounting_job_status(18500)

	assert result['pid'] == '18500'
	assert result['state'] == 'SUCCESS'
	assert result['exit_code'] == 0
	assert result['elapsed_time'] == 156

	assert calls[0]['url'] == (
		'http://127.0.0.1:6820/'
		'slurmdb/v0.0.36/job/18500'
	)


@pytest.mark.parametrize(
	'raw_state,exit_code,exit_status,expected',
	[
		('COMPLETED', 1, 'ERROR', 'FAILURE'),
		('COMPLETED', 0, 'ERROR', 'FAILURE'),
		('FAILED', 1, 'ERROR', 'FAILURE'),
		('NODE_FAIL', 1, 'ERROR', 'FAILURE'),
		('OUT_OF_MEMORY', 1, 'ERROR', 'FAILURE'),
		('TIMEOUT', 1, 'ERROR', 'TIMED-OUT'),
		('CANCELLED', 0, 'SUCCESS', 'CANCELED')
	]
)
def test_accounting_terminal_mapping(
		monkeypatch,
		raw_state,
		exit_code,
		exit_status,
		expected):

	client, _ = make_client(
		monkeypatch,
		{
			'errors': [],
			'jobs': [
				accounting_job(
					state=raw_state,
					exit_code=exit_code,
					exit_status=exit_status
				)
			]
		}
	)

	result = client.get_accounting_job_status(18500)

	assert result is not None
	assert result['state'] == expected


@pytest.mark.parametrize(
	'payload',
	[
		{'errors': [{'error_number': 1007}], 'jobs': []},
		{'errors': [], 'jobs': []},
		{'errors': [], 'jobs': [accounting_job(99999)]},
		{'errors': [], 'jobs': [accounting_job(), accounting_job()]},
		{'errors': [], 'jobs': [accounting_job(state='RUNNING')]},
		{'errors': [], 'jobs': [accounting_job(exit_code=None)]},
		{'errors': [], 'jobs': [accounting_job(exit_code=-1)]},
		{'errors': [], 'jobs': [accounting_job(exit_code='0')]},
		{'errors': [], 'jobs': [accounting_job(exit_code=0, exit_status='')]},
		{'errors': [], 'jobs': 'invalid'},
		{'errors': []},
		[]
	]
)
def test_unusable_accounting_reply_returns_none(
		monkeypatch, payload):

	client, _ = make_client(monkeypatch, payload)

	assert client.get_accounting_job_status(18500) is None


def test_accounting_http_failure(monkeypatch):
	client, _ = make_client(
		monkeypatch,
		{'errors': [], 'jobs': [accounting_job()]},
		status_code=503
	)

	assert client.get_accounting_job_status(18500) is None


def test_invalid_job_id_never_calls_rest(monkeypatch):
	client, calls = make_client(
		monkeypatch,
		{'errors': [], 'jobs': [accounting_job()]}
	)

	for invalid_id in ('', '../jobs', '18500/other', -1, True):
		assert client.get_accounting_job_status(invalid_id) is None

	assert calls == []
