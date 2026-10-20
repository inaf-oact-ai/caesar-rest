"""Focused H2D-A tests: no real MongoDB or job submission required."""
import hashlib
from types import SimpleNamespace

import pytest

from caesar_rest import pipeline_artifact_retention as retention
from caesar_rest import pipeline_manager as manager


class Runs:
	def __init__(self, run):
		self.run = run

	def find_one(self, query):
		return self.run

	def update_one(self, query, changes):
		assert query['retained_artifacts'] == {'$exists': False}
		self.run.update(changes['$set'])
		return SimpleNamespace(modified_count=1)


class DB:
	def __init__(self, run):
		self.pipeline_runs = Runs(run)


def test_retention_copies_only_registered_content(tmp_path, monkeypatch):

	run = {
		'status': 'COMPLETED', 
		'artifacts_registered_at': 'now',
		'artifacts': [{
			'name': 'manifest', 
			'relative_path': 'results/a.json',
			'size_bytes': 2
		}]
	}
	
	db = DB(run)
	monkeypatch.setattr(retention.access, 'get_run', lambda *args: run)
	import io
	monkeypatch.setattr(retention.access, 'open_registered_artifact', lambda *args: (io.BytesIO(b'{}'), 'a.json', 'application/json'))
	result = retention.promote_run(db, 'tester', 'pipeline1', 'getinfo', 'run1', str(tmp_path / 'retained'))
	assert result['count'] == 1
	assert (tmp_path / 'retained' / 'tester' / 'pipeline1' / 'run1' / '0000').read_bytes() == b'{}'
	assert run['retained_artifacts'][0]['sha256'] == hashlib.sha256(b'{}').hexdigest()
	assert retention.promote_run(db, 'tester', 'pipeline1', 'getinfo', 'run1', str(tmp_path / 'retained'))['already_retained']


def test_refuses_unsafe_identity(tmp_path):
	with pytest.raises(manager.PipelineError):
		retention.retained_directory(str(tmp_path), '../someone', 'p1', 'r1')


def test_refuses_large_files(tmp_path, monkeypatch):
	
	run = {
		'status': 'COMPLETED', 
		'artifacts_registered_at': 'now',
		'artifacts': [{
			'size_bytes': 5
		}]
	}
	
	monkeypatch.setattr(retention.access, 'get_run', lambda *args: run)
	with pytest.raises(manager.PipelineError) as exc:
		retention.promote_run(DB(run), 'tester', 'pipeline1', 'getinfo', 'run1', str(tmp_path / 'retained'), max_file_bytes=2)
	assert exc.value.status == 413


def test_no_db_commit_on_changed_content(tmp_path, monkeypatch):
	run = {
		'status': 'COMPLETED', 
		'artifacts_registered_at': 'now',
		'artifacts': [{
			'size_bytes': 2
		}]
	}
	
	monkeypatch.setattr(retention.access, 'get_run', lambda *args: run)
	import io
	monkeypatch.setattr(retention.access, 'open_registered_artifact', lambda *args: (io.BytesIO(b'abc'), 'a.json', 'application/json'))
	with pytest.raises(manager.PipelineError):
		retention.promote_run(DB(run), 'tester', 'pipeline1', 'getinfo', 'run1', str(tmp_path / 'retained'))
	assert 'retained_artifacts' not in run
