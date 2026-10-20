"""H2C2b2b2-B2: atomic one-shot submission intent tests (no Slurm calls)."""
from types import SimpleNamespace

import pytest

from caesar_rest import pipeline_job_binding as binding
from caesar_rest import pipeline_manager as manager
from caesar_rest import pipeline_v2_slurm_submission as submission


class Runs:
	def __init__(self):
		self.record = {
			'owner': 'alice', 'pipeline_id': 'p1', 'run_id': 'r1',
			'status': 'SUBMITTING', 'submission_token': 'a' * 32
		}
		self.modified = 0

	def update_one(self, query, update):
		if all(self.record.get(k) == v for k, v in query.items() if k != 'submission_intent') and 'submission_intent' not in self.record:
			self.record.update(update['$set'])
			self.modified += 1
			return SimpleNamespace(modified_count=1)
		return SimpleNamespace(modified_count=0)


def _prepared(token='a' * 32):
	return {
		'claim': binding.SubmissionClaim('alice', 'p1', 'r1', token),
		'assets': {
			'version': 2, 'run_id': 'r1', 'job_id': 'j1',
			'workspace_cluster': '/jobs/job_j1',
			'staging_spec_cluster': '/jobs/job_j1/staging_spec.json',
			'execution_spec_cluster': '/jobs/job_j1/execution_spec.json',
			'worker_cluster': '/jobs/job_j1/caesar-pipeline-worker.pyz',
			'worker_sha256': 'f' * 64
		}
	}


class Scheduler:
	cluster_batch_workdir = '/home/slurm'

	def __init__(self, reply):
		self.reply = reply
		self.calls = 0

	def check_submit_vars(self):
		return 0

	def submit_job(self, payload):
		self.calls += 1
		return self.reply


@pytest.fixture
def db(monkeypatch):
	runs = Runs()
	monkeypatch.setattr(manager, 'collections', lambda: (None, runs, None))
	return runs


def test_atomic_intent_is_one_shot(db):
	p = _prepared()
	first = binding.begin_submission_intent(p['claim'], p['assets'])
	assert first['job_id'] == 'j1'
	assert first['worker_sha256'] == 'f' * 64
	assert db.modified == 1
	with pytest.raises(manager.PipelineError) as exc:
		binding.begin_submission_intent(p['claim'], p['assets'])
	assert exc.value.status == 409
	assert db.modified == 1


def test_stale_claim_cannot_reserve(db):
	with pytest.raises(manager.PipelineError):
		binding.begin_submission_intent(_prepared('b' * 32)['claim'], _prepared()['assets'])
	assert 'submission_intent' not in db.record


def test_duplicate_never_contacts_scheduler(db, monkeypatch):
	monkeypatch.setattr(binding, 'finish_submission', lambda *args: None)
	monkeypatch.setattr(binding, 'fail_submission', lambda *args, **kwargs: None)
	p = _prepared()
	scheduler = Scheduler({'job_id': 123, 'errors': []})
	submission.submit_claimed_v2(p, scheduler, 'pipeline1')
	assert scheduler.calls == 1
	with pytest.raises(manager.PipelineError) as exc:
		submission.submit_claimed_v2(p, scheduler, 'pipeline1')
	assert exc.value.status == 409
	assert scheduler.calls == 1


def test_unknown_scheduler_reply_keeps_intent(db, monkeypatch):
	monkeypatch.setattr(binding, 'fail_submission', lambda *args, **kwargs: None)
	with pytest.raises(manager.PipelineError):
		submission.submit_claimed_v2(_prepared(), Scheduler(None), 'pipeline1')
	assert 'submission_intent' in db.record


def test_preflight_error_leaves_claim_for_investigation(db, monkeypatch):
	monkeypatch.setattr(binding, 'fail_submission', lambda *args, **kwargs: pytest.fail('Must not mutate run on preflight'))
	scheduler = Scheduler({'job_id': 123})
	with pytest.raises(manager.PipelineError):
		submission.submit_claimed_v2(_prepared(), scheduler, 'invalid job')
	assert scheduler.calls == 0
	assert 'submission_intent' not in db.record
