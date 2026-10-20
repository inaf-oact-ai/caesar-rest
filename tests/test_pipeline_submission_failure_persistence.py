"""Regression tests for pipeline submission failure persistence."""

from types import SimpleNamespace

import pytest

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.submission import job_binding as binding


class FakeRuns:
	def __init__(self, modified_count):
		self.modified_count = modified_count
		self.query = None
		self.update = None

	def update_one(self, query, update):
		self.query = query
		self.update = update
		return SimpleNamespace(modified_count=self.modified_count)


@pytest.fixture
def setup_runs(monkeypatch):
	def make(modified_count):
		runs = FakeRuns(modified_count)
		monkeypatch.setattr(
			manager,
			'collections',
			lambda: (None, runs, None)
		)
		return runs
	return make


def test_failed_submission_is_persisted(setup_runs):
	runs = setup_runs(1)
	claim = binding.SubmissionClaim(
		'alice', 'p1', 'r1', 'a' * 32
	)

	binding.fail_submission(
		claim,
		'Slurm rejected submission',
		uncertain=False,
		job_id='j1'
	)

	assert runs.query['status'] == 'SUBMITTING'
	assert runs.query['submission_token'] == claim.token
	assert runs.update['$set']['status'] == 'SUBMISSION_FAILED'
	assert runs.update['$set']['job_id'] == 'j1'
	assert 'submission_token' in runs.update['$unset']


def test_uncertain_submission_is_persisted(setup_runs):
	runs = setup_runs(1)
	claim = binding.SubmissionClaim(
		'alice', 'p1', 'r1', 'a' * 32
	)

	binding.fail_submission(
		claim,
		'Slurm submission outcome unknown',
		uncertain=True,
		job_id='j1'
	)

	assert runs.update['$set']['status'] == 'SUBMISSION_UNCERTAIN'
	assert runs.update['$set']['job_id'] == 'j1'


def test_failed_conditional_update_is_reported(setup_runs):
	setup_runs(0)
	claim = binding.SubmissionClaim(
		'alice', 'p1', 'r1', 'a' * 32
	)

	with pytest.raises(
		manager.PipelineError,
		match='failure state could not be recorded'
	):
		binding.fail_submission(
			claim,
			'Slurm outcome uncertain',
			uncertain=True,
			job_id='j1'
		)
