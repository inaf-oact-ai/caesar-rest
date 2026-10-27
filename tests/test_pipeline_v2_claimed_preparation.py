"""Claim/preparation sequencing without Slurm or disk writes."""
from types import SimpleNamespace
import pytest

from caesar_rest.pipeline.submission import claimed_preparation as claimed
from caesar_rest.pipeline import manager


def _run():
	return {'application': 'oxkat', 'parameters': {'run': True},
		'input_artifacts': [{'input_name': 'vis'}], 'dataset_id': None}


def _args():
	return ('alice', 'p1', 'stage2', 'r2', 'job123',
		'/jobs', '/cluster/jobs', '/retained', '/cluster/retained',
		'/containers/image.sif', ['--run'], {'ms': 'vis'})


def _setup(monkeypatch, run=None):
	run = _run() if run is None else run
	monkeypatch.setattr(claimed.manager, 'get_pipeline', lambda owner, pid: {'pipeline_id': pid})
	monkeypatch.setattr(claimed, 'db_unused', None, raising=False)
	calls = []
	class Runs:
		def find_one(self, query):
			calls.append(('read', query.copy()))
			return run
	db = SimpleNamespace(pipeline_runs=Runs())
	claim = SimpleNamespace(token='secret-token', owner='alice', pipeline_id='p1', run_id='r2')
	def fake_claim(*args, **kwargs):
		calls.append(('claim', args, kwargs))
		return claim
	def fake_prepare(*args, **kwargs):
		calls.append(('prepare', args, kwargs))
		return {'version': 2, 'worker_sha256': 'abc'}
	def fake_failure(*args, **kwargs):
		calls.append(('failure', args, kwargs))
	monkeypatch.setattr(claimed.job_binding, 'claim_run', fake_claim)
	monkeypatch.setattr(claimed.preparation, 'prepare_v2_submission', fake_prepare)
	monkeypatch.setattr(claimed.job_binding, 'fail_submission', fake_failure)
	return db, calls, claim


def test_claim_occurs_before_preparation(monkeypatch):
	db, calls, claim = _setup(monkeypatch)
	result = claimed.claim_and_prepare_v2(db, *_args())
	assert [x[0] for x in calls] == ['read', 'claim', 'prepare']
	assert calls[2][2]['submission_token'] == claim.token
	assert result['claim'] is claim
	assert result['assets']['version'] == 2


def test_failed_preparation_records_failure(monkeypatch):
	db, calls, claim = _setup(monkeypatch)
	def fail(*args, **kwargs):
		raise manager.PipelineError('storage failure', 503)
	monkeypatch.setattr(claimed.preparation, 'prepare_v2_submission', fail)
	with pytest.raises(manager.PipelineError):
		claimed.claim_and_prepare_v2(db, *_args())
	assert [x[0] for x in calls] == ['read', 'claim', 'failure']
	assert calls[-1][1][0] is claim
	assert calls[-1][2]['uncertain'] is False


def test_unbound_run_is_rejected_without_claim(monkeypatch):
	run = _run()
	run['input_artifacts'] = []
	db, calls, _ = _setup(monkeypatch, run)
	with pytest.raises(manager.PipelineError):
		claimed.claim_and_prepare_v2(db, *_args())
	assert [x[0] for x in calls] == ['read']


def test_mixed_dataset_claim_and_preparation(monkeypatch):
	run = _run()
	run['dataset_id'] = 'dataset1'

	db, calls, _ = _setup(monkeypatch, run)

	result = claimed.claim_and_prepare_v2(
		db, *_args(),
		dataset_app_root='/data/app',
		dataset_cluster_root='/data/cluster',
		dataset_input_name='measurement_set'
	)

	assert [x[0] for x in calls] == [
		'read', 'claim', 'prepare'
	]

	assert calls[1][2]['dataset_id'] == 'dataset1'
	assert calls[1][2]['require_dataset_binding'] is True

	assert calls[2][2]['dataset_app_root'] == '/data/app'
	assert calls[2][2]['dataset_cluster_root'] == '/data/cluster'
	assert calls[2][2]['dataset_input_name'] == 'measurement_set'

	assert result['assets']['version'] == 2
	
	
def test_dataset_only_claim_and_preparation(monkeypatch):
	run = _run()
	run['dataset_id'] = 'dataset1'
	run['input_artifacts'] = []

	db, calls, _ = _setup(monkeypatch, run)

	result = claimed.claim_and_prepare_v2(
		db, *_args(),
		dataset_app_root='/data/app',
		dataset_cluster_root='/data/cluster'
	)

	assert [x[0] for x in calls] == [
		'read', 'claim', 'prepare'
	]

	assert calls[1][2]['dataset_id'] == 'dataset1'
	assert calls[1][2]['require_dataset_binding'] is True
	assert result['assets']['version'] == 2
