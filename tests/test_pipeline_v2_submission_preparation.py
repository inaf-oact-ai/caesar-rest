"""H2C2b2b1: preparation-only tests; never submit a scheduler job."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.submission import v2_preparation as prep


class FakeRuns:
	def __init__(self, run):
		self.run = run
		self.queries = []

	def find_one(self, query):
		self.queries.append(query)
		if (query.get('owner') == 'alice' and query.get('pipeline_id') == 'p1'
				and query.get('node_id') == 'stage2' and query.get('run_id') == 'r2'
				and query.get('status') == self.run['status']):
			return self.run
		return None


def _case(tmp_path, monkeypatch, status='PLANNED'):
	run = {'owner': 'alice', 'pipeline_id': 'p1', 'node_id': 'stage2',
		'run_id': 'r2', 'status': status, 'input_artifacts': [{'input_name': 'vis'}]}
	db = SimpleNamespace(pipeline_runs=FakeRuns(run))
	monkeypatch.setattr(prep.manager, 'get_pipeline', lambda owner, pipeline: {'pipeline_id': pipeline})
	monkeypatch.setattr(prep.adapter, 'build_bound_v2_specs', lambda *a, **kw: (
		{'version': 2, 'inputs': [{'name': 'vis'}]},
		{'version': 2, 'input_options': {'ms': 'vis'}}
	))
	monkeypatch.setattr(prep.worker_bundle, 'deploy_worker', lambda ws: {
		'name': 'caesar-pipeline-worker.pyz', 'sha256': '0' * 64,
		'path': str(Path(ws, 'caesar-pipeline-worker.pyz'))
	})
	root = tmp_path / 'jobs'
	root.mkdir()
	return db, root, run


def _call(db, root, **kwargs):
	return prep.prepare_v2_submission(db, 'alice', 'p1', 'stage2', 'r2',
		'j2', str(root), '/cluster/jobs', '/retained/app', '/retained/cluster',
		'/images/science.sif', ['--run'], {'ms': 'vis'}, **kwargs)


def test_preparation_creates_exclusive_worker_and_specs(tmp_path, monkeypatch):
	db, root, run = _case(tmp_path, monkeypatch)
	monkeypatch.setattr(prep.worker_bundle, 'deploy_worker', lambda ws: {
		'name': 'caesar-pipeline-worker.pyz',
		'sha256': '0' * 64,
		'path': str(Path(ws, 'caesar-pipeline-worker.pyz'))
	})
	result = _call(db, root)
	assert result['version'] == 2
	assert result['workspace_cluster'] == '/cluster/jobs/job_j2'
	assert (root / 'job_j2' / 'staging_spec.json').is_file()
	assert (root / 'job_j2' / 'execution_spec.json').is_file()
	assert run['status'] == 'PLANNED'
	assert db.pipeline_runs.queries[0]['owner'] == 'alice'


def test_preparation_cannot_reuse_workspace(tmp_path, monkeypatch):
	db, root, _ = _case(tmp_path, monkeypatch)
	(root / 'job_j2').mkdir()
	with pytest.raises(manager.PipelineError, match='already exists'):
		_call(db, root)


def test_preparation_rejects_wrong_owner_before_disk_write(tmp_path, monkeypatch):
	db, root, _ = _case(tmp_path, monkeypatch)
	with pytest.raises(manager.PipelineError):
		prep.prepare_v2_submission(db, 'bob', 'p1', 'stage2', 'r2',
			'j2', str(root), '/cluster/jobs', '/retained/app', '/retained/cluster',
			'/images/science.sif', ['--run'], {'ms': 'vis'})
	assert not (root / 'job_j2').exists()


def test_preparation_failure_keeps_unpublished_workspace(tmp_path, monkeypatch):
	db, root, _ = _case(tmp_path, monkeypatch)
	def fail(*args, **kwargs):
		raise ValueError('simulated spec failure')
	monkeypatch.setattr(prep.adapter, 'build_bound_v2_specs', fail)
	with pytest.raises(manager.PipelineError, match='inspect reserved workspace'):
		_call(db, root)
	assert (root / 'job_j2').is_dir()
	assert not (root / 'job_j2' / 'staging_spec.json').exists()


def test_invalid_job_id_rejected(tmp_path, monkeypatch):
	db, root, _ = _case(tmp_path, monkeypatch)
	with pytest.raises(manager.PipelineError):
		prep.prepare_v2_submission(db, 'alice', 'p1', 'stage2', 'r2',
		'../../escape', str(root), '/cluster/jobs', '/retained/app', '/retained/cluster',
		'/images/science.sif', ['--run'], {'ms': 'vis'})
	assert list(root.iterdir()) == []
