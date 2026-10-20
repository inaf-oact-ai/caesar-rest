"""Read-only reconciliation: no DB mutation or scheduler submission."""
from types import SimpleNamespace

import pytest

from caesar_rest import pipeline_manager as manager
from caesar_rest import pipeline_v2_reconciliation as reconciliation


class Runs:
	def __init__(self, run):
		self.run = run
		self.queries = []

	def find_one(self, query):
		self.queries.append(query)
		if query['owner'] != 'alice':
			return None
		return self.run

	def update_one(self, *args, **kwargs):
		raise AssertionError('Read-only code must not write MongoDB')


class Scheduler:
	def __init__(self, reply):
		self.reply = reply
		self.calls = []

	def get_job_status(self, pid):
		self.calls.append(pid)
		if isinstance(self.reply, Exception):
			raise self.reply
		return self.reply

	def submit_job(self, *args):
		raise AssertionError('Must not submit')


def sample(pid=None, status='SUBMISSION_UNCERTAIN'):
	return {
		'run_id': 'run1', 'status': status, 'job_id': 'j1',
		'scheduler_pid': pid,
		'submission_intent': {
			'attempt_id': 'a' * 32,
			'worker_sha256': 'b' * 64,
			'job_id': 'j1'
		}
	}


@pytest.fixture(autouse=True)
def pipeline_lookup(monkeypatch):
	monkeypatch.setattr(manager, 'get_pipeline', lambda owner, pipeline_id: {'owner': owner})


def inspect(run, scheduler, owner='alice'):
	return reconciliation.inspect_v2_submission(
		SimpleNamespace(pipeline_runs=Runs(run)), owner, 'p1', 'stage1', 'run1', scheduler)


def test_without_pid_remains_unresolved():
	s = Scheduler(None)
	result = inspect(sample(), s)
	assert result['outcome'] == 'UNRESOLVED'
	assert not result['can_auto_retry']
	assert s.calls == []


def test_matching_pid_is_evidence_not_final_confirmation():
	s = Scheduler({'pid': 123, 'state': 'RUNNING'})
	result = inspect(sample(123), s)
	assert result['outcome'] == 'PID_FOUND'
	assert result['scheduler_evidence'] == {'pid': 123, 'state': 'RUNNING'}
	assert result['can_auto_finalize'] is False
	assert s.calls == ['123']


def test_missing_slurm_record_is_not_rejection():
	result = inspect(sample(123), Scheduler(None))
	assert result['outcome'] == 'UNRESOLVED'


def test_wrong_pid_is_not_accepted():
	result = inspect(sample(123), Scheduler({'pid': 124, 'state': 'RUNNING'}))
	assert result['outcome'] == 'UNRESOLVED'


def test_scheduler_error_is_not_rejection():
	result = inspect(sample(123), Scheduler(TimeoutError('timeout')))
	assert result['outcome'] == 'UNRESOLVED'


def test_owner_scope_enforced():
	with pytest.raises(manager.PipelineError) as exc:
		inspect(sample(123), Scheduler(None), owner='bob')
	assert exc.value.status == 404


def test_missing_intent_rejected():
	run = sample()
	run.pop('submission_intent')
	with pytest.raises(manager.PipelineError):
		inspect(run, Scheduler(None))


def test_conflicting_job_id_rejected():
	run = sample()
	run['job_id'] = 'different'
	with pytest.raises(manager.PipelineError):
		inspect(run, Scheduler(None))
