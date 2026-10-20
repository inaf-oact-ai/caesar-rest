"""State-machine regression tests for pipeline submission claims."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.submission import job_binding as binding


class Runs:
	def __init__(self):
		self.record = {
			'owner': 'alice',
			'pipeline_id': 'p1',
			'run_id': 'r1',
			'application': 'oxkat',
			'parameters': {'threshold': 5},
			'status': 'PLANNED'
		}

	def find_one(self, query):
		if self._matches(query):
			return deepcopy(self.record)
		return None

	def _matches(self, query):
		for key, expected in query.items():
			if isinstance(expected, dict) and '$exists' in expected:
				if (key in self.record) != expected['$exists']:
					return False
			elif self.record.get(key) != expected:
				return False
		return True

	def update_one(self, query, update):
		if not self._matches(query):
			return SimpleNamespace(modified_count=0)

		for key, value in update.get('$set', {}).items():
			self.record[key] = value

		for key in update.get('$unset', {}):
			self.record.pop(key, None)

		return SimpleNamespace(modified_count=1)


@pytest.fixture
def runs(monkeypatch):
	collection = Runs()

	monkeypatch.setattr(
		manager, 'collections',
		lambda: (None, collection, None)
	)

	monkeypatch.setattr(
		manager, 'get_pipeline',
		lambda owner, pipeline_id: {'owner': owner, 'pipeline_id': pipeline_id}
	)

	return collection


def test_only_one_claim_can_succeed(runs):
	first = binding.claim_run(
		'alice', 'p1', 'r1', 'oxkat',
		{'threshold': 5}
	)

	assert runs.record['status'] == 'SUBMITTING'
	assert runs.record['submission_token'] == first.token

	with pytest.raises(manager.PipelineError) as exc:
		binding.claim_run(
			'alice', 'p1', 'r1', 'oxkat',
			{'threshold': 5}
		)

	assert exc.value.status == 409
	assert runs.record['submission_token'] == first.token


def test_stale_claim_cannot_finish_submission(runs):
	first = binding.claim_run(
		'alice', 'p1', 'r1', 'oxkat',
		{'threshold': 5}
	)

	stale = binding.SubmissionClaim(
		'alice', 'p1', 'r1', 'b' * 32
	)

	with pytest.raises(manager.PipelineError):
		binding.finish_submission(
			stale, 'j1', 'slurm', 123
		)

	assert runs.record['status'] == 'SUBMITTING'
	assert runs.record['submission_token'] == first.token
	assert 'scheduler_pid' not in runs.record


def test_stale_claim_cannot_record_failure(runs):
	first = binding.claim_run(
		'alice', 'p1', 'r1', 'oxkat',
		{'threshold': 5}
	)

	stale = binding.SubmissionClaim(
		'alice', 'p1', 'r1', 'b' * 32
	)

	with pytest.raises(manager.PipelineError):
		binding.fail_submission(
			stale,
			'Simulated timeout',
			uncertain=True,
			job_id='j1'
		)

	assert runs.record['status'] == 'SUBMITTING'
	assert runs.record['submission_token'] == first.token


def test_successful_submission_is_terminal_for_claim(runs):
	claim = binding.claim_run(
		'alice', 'p1', 'r1', 'oxkat',
		{'threshold': 5}
	)

	binding.finish_submission(
		claim, 'j1', 'slurm', 123
	)

	assert runs.record['status'] == 'SUBMITTED'
	assert runs.record['job_id'] == 'j1'
	assert runs.record['scheduler_pid'] == 123
	assert 'submission_token' not in runs.record

	with pytest.raises(manager.PipelineError):
		binding.fail_submission(
			claim,
			'Late timeout',
			uncertain=True,
			job_id='j1'
		)

	assert runs.record['status'] == 'SUBMITTED'
	assert runs.record['scheduler_pid'] == 123


def test_uncertain_submission_cannot_be_finalized_by_old_claim(runs):
	claim = binding.claim_run(
		'alice', 'p1', 'r1', 'oxkat',
		{'threshold': 5}
	)

	binding.fail_submission(
		claim,
		'Scheduler outcome unknown',
		uncertain=True,
		job_id='j1'
	)

	assert runs.record['status'] == 'SUBMISSION_UNCERTAIN'
	assert 'submission_token' not in runs.record

	with pytest.raises(manager.PipelineError):
		binding.finish_submission(
			claim, 'j1', 'slurm', 123
		)

	assert runs.record['status'] == 'SUBMISSION_UNCERTAIN'
	assert 'scheduler_pid' not in runs.record


def test_failure_preserves_durable_intent(runs):
	claim = binding.claim_run(
		'alice', 'p1', 'r1', 'oxkat',
		{'threshold': 5}
	)

	assets = {
		'version': 2,
		'run_id': 'r1',
		'job_id': 'j1',
		'worker_sha256': 'a' * 64
	}

	intent = binding.begin_submission_intent(
		claim, assets
	)

	binding.fail_submission(
		claim,
		'Scheduler timeout',
		uncertain=True,
		job_id='j1'
	)

	assert runs.record['status'] == 'SUBMISSION_UNCERTAIN'
	assert runs.record['submission_intent'] == intent
	assert 'submission_token' not in runs.record
