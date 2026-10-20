"""Mocked-only integration: no REST routes and no Slurm network traffic."""
import json
from types import SimpleNamespace

import pytest

from caesar_rest import pipeline_v2_slurm_submission as submission
from caesar_rest import pipeline_job_binding as binding
from caesar_rest import pipeline_manager as manager


def _prepared():
	claim = binding.SubmissionClaim('alice', 'p1', 'run1', 'a' * 32)
	return {'claim': claim, 'assets': {
		'version': 2, 'run_id': 'run1', 'job_id': 'j1',
		'workspace_cluster': '/jobs/job_j1',
		'staging_spec_cluster': '/jobs/job_j1/staging_spec.json',
		'execution_spec_cluster': '/jobs/job_j1/execution_spec.json',
		'worker_cluster': '/jobs/job_j1/caesar-pipeline-worker.pyz',
		'worker_sha256': 'a' * 64
	}}


class Scheduler:
	cluster_batch_workdir = '/home/slurm'

	def __init__(self, result):
		self.result = result
		self.calls = []

	def check_submit_vars(self):
		return 0

	def submit_job(self, payload):
		self.calls.append(json.loads(payload))
		if isinstance(self.result, Exception):
			raise self.result
		return self.result


@pytest.fixture
def events(monkeypatch):
	items = []
	monkeypatch.setattr(binding, 'finish_submission', lambda *a: items.append(('finish', a[1:])))
	monkeypatch.setattr(binding, 'fail_submission', lambda *a, **k: items.append(('fail', k)))
	return items


def test_script_stages_before_execution_and_checks_worker():
	p = json.loads(submission.build_v2_slurm_payload(_prepared()['assets'], 'pipeline1', '/home/slurm'))
	lines = p['script'].splitlines()
	assert lines[0:2] == ['#!/bin/bash', 'set -e']
	assert 'sha256sum -c --status' in lines[2]
	assert " prepare " in lines[3]
	assert " execute " in lines[4]
	assert p['job']['name'] == 'pipeline1'


def test_scheduler_accepts(events):
	s = Scheduler({'job_id': 123, 'errors': []})
	result = submission.submit_claimed_v2(_prepared(), s, 'pipeline1')
	assert result['status'] == 'SUBMITTED'
	assert result['scheduler_pid'] == 123
	assert [e[0] for e in events] == ['finish']
	assert len(s.calls) == 1


def test_timeout_like_missing_reply_is_uncertain(events):
	s = Scheduler(None)
	with pytest.raises(manager.PipelineError):
		submission.submit_claimed_v2(_prepared(), s, 'pipeline1')
	assert events == [('fail', {'uncertain': True, 'job_id': 'j1'})]


def test_explicit_rejection_is_definite(events):
	s = Scheduler({'errors': [{'error': 'invalid partition'}]})
	with pytest.raises(manager.PipelineError):
		submission.submit_claimed_v2(_prepared(), s, 'pipeline1')
	assert events == [('fail', {'uncertain': False, 'job_id': 'j1'})]


def test_exception_after_request_is_uncertain(events):
	s = Scheduler(TimeoutError('timeout'))
	with pytest.raises(manager.PipelineError):
		submission.submit_claimed_v2(_prepared(), s, 'pipeline1')
	assert events == [('fail', {'uncertain': True, 'job_id': 'j1'})]


def test_invalid_payload_does_not_call_scheduler(events):
	s = Scheduler({'job_id': 1})
	with pytest.raises(manager.PipelineError):
		submission.submit_claimed_v2(_prepared(), s, 'bad job name')
	assert s.calls == []
	assert events == [('fail', {'uncertain': False, 'job_id': 'j1'})]
