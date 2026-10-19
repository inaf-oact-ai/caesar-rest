"""Isolated registration tests: no MongoDB or Slurm required."""
from types import SimpleNamespace

import pytest

from caesar_rest import pipeline_artifact_registration as reg


class Collection:
	def __init__(self, doc):
		self.doc = doc
		self.updates = 0

	def find_one(self, query):
		if self.doc is None:
			return None
		for key, value in query.items():
			if self.doc.get(key) != value:
				return None
		return dict(self.doc)

	def update_one(self, query, change):
		if self.find_one(query) is None:
			return SimpleNamespace(modified_count=0)
		self.doc.update(change['$set'])
		self.updates += 1
		return SimpleNamespace(modified_count=1)


class DB:
	def __init__(self, run, job):
		self.pipeline_runs = Collection(run)
		self.jobs = Collection(job)

	def __getitem__(self, key):
		assert key == 'tester.jobs'
		return self.jobs


def fixtures(tmp_path):
	root = tmp_path / 'job_root'
	jobdir = root / 'job_abc'
	results = jobdir / 'results'
	results.mkdir(parents=True)
	(results / 'project_info.json').write_text('{}')
	run = dict(owner='tester', pipeline_id='pipe', run_id='run', job_id='abc',
		application='oxkat', status='COMPLETED', artifacts=[])
	job = dict(job_id='abc', pipeline_id='pipe', run_id='run',
		execution_mode='staged_container', app='oxkat', state='SUCCESS',
		exit_code=0, job_top_dir=str(root))
	contract = {'project_info': {'path': 'project_info.json', 'required': True,
		'type': 'application/json'}}
	return DB(run, job), contract, results


def test_registers_once(tmp_path):
	db, contract, _ = fixtures(tmp_path)
	assert reg.register_completed_run(db, 'tester', 'pipe', 'run', 'abc', contract)
	assert db.pipeline_runs.doc['artifacts'][0]['relative_path'] == 'results/project_info.json'
	assert not reg.register_completed_run(db, 'tester', 'pipe', 'run', 'abc', contract)
	assert db.pipeline_runs.updates == 1


def test_missing_required_does_not_publish(tmp_path):
	db, contract, results = fixtures(tmp_path)
	(results / 'project_info.json').unlink()
	with pytest.raises(reg.discovery.ArtifactDiscoveryError):
		reg.register_completed_run(db, 'tester', 'pipe', 'run', 'abc', contract)
	assert db.pipeline_runs.doc['artifacts'] == []


def test_other_owner_cannot_register(tmp_path):
	db, contract, _ = fixtures(tmp_path)
	assert not reg.register_completed_run(db, 'other', 'pipe', 'run', 'abc', contract)
	assert db.pipeline_runs.updates == 0


def test_non_staged_job_ignored(tmp_path):
	db, contract, _ = fixtures(tmp_path)
	db.jobs.doc.pop('execution_mode')
	assert not reg.register_completed_run(db, 'tester', 'pipe', 'run', 'abc', contract)


def test_non_success_job_ignored(tmp_path):
	db, contract, _ = fixtures(tmp_path)
	db.jobs.doc['state'] = 'FAILURE'
	assert not reg.register_completed_run(db, 'tester', 'pipe', 'run', 'abc', contract)
