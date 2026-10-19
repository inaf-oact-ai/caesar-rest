import io
import os
from types import SimpleNamespace

import pytest

from caesar_rest import pipeline_artifact_access as access


class Collection:
	def __init__(self, doc):
		self.doc = doc

	def find_one(self, query):
		if self.doc and all(self.doc.get(k) == v for k, v in query.items()):
			return self.doc
		return None


class DB:
	def __init__(self, run, job):
		self.pipeline_runs = Collection(run)
		self.jobs = Collection(job)

	def __getitem__(self, name):
		return self.jobs


def fixture(tmp_path):
	owner = 'tester'
	job_id = 'abc123'
	top = tmp_path / 'jobs'
	workspace = top / ('job_' + job_id)
	results = workspace / 'results'
	results.mkdir(parents=True)
	(results / 'report.json').write_bytes(b'{}')
	run = {
		'owner': owner, 'pipeline_id': 'p1', 'node_id': 'getinfo', 'run_id': 'r1',
		'job_id': job_id, 'application': 'oxkat', 'status': 'COMPLETED',
		'artifact_workspace': str(workspace),
		'artifacts': [{'name': 'manifest', 'relative_path': 'results/report.json',
			'type': 'application/json', 'size_bytes': 2}]
	}
	job = {'job_id': job_id, 'pipeline_id': 'p1', 'run_id': 'r1',
		'execution_mode': 'staged_container', 'app': 'oxkat', 'job_top_dir': str(top)}
	return DB(run, job), run, results


def test_lists_artifacts_without_workspace(tmp_path):
	_, run, _ = fixture(tmp_path)
	assert access.public_artifacts(run) == [{
		'index': 0, 'name': 'manifest', 'relative_path': 'results/report.json',
		'type': 'application/json', 'size_bytes': 2
	}]


def test_reads_registered_file(tmp_path):
	db, run, _ = fixture(tmp_path)
	fileobj, filename, mime = access.open_registered_artifact(db, 'tester', run, 0)
	with fileobj:
		assert fileobj.read() == b'{}'
	assert filename == 'report.json'
	assert mime == 'application/json'


def test_rejects_unregistered_index(tmp_path):
	db, run, _ = fixture(tmp_path)
	with pytest.raises(access.ArtifactAccessError) as exc:
		access.open_registered_artifact(db, 'tester', run, 5)
	assert exc.value.status == 404


def test_rejects_traversal(tmp_path):
	db, run, _ = fixture(tmp_path)
	run['artifacts'][0]['relative_path'] = 'results/../private.txt'
	with pytest.raises(access.ArtifactAccessError):
		access.open_registered_artifact(db, 'tester', run, 0)


def test_rejects_symlink(tmp_path):
	db, run, results = fixture(tmp_path)
	(results / 'report.json').unlink()
	(results / 'report.json').symlink_to(tmp_path / 'secret')
	with pytest.raises(access.ArtifactAccessError):
		access.open_registered_artifact(db, 'tester', run, 0)


def test_missing_file_returns_gone(tmp_path):
	db, run, results = fixture(tmp_path)
	(results / 'report.json').unlink()
	with pytest.raises(access.ArtifactAccessError) as exc:
		access.open_registered_artifact(db, 'tester', run, 0)
	assert exc.value.status == 410


def test_detects_changed_file_size(tmp_path):
	db, run, results = fixture(tmp_path)
	(results / 'report.json').write_bytes(b'changed')
	with pytest.raises(access.ArtifactAccessError):
		access.open_registered_artifact(db, 'tester', run, 0)
