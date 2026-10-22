"""Unit tests for H2B selection resolution; no Slurm or Flask server."""

import io
import pytest

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import resolver


class Collection:
	def __init__(self, doc):
		self.doc = doc

	def find_one(self, query):
		if self.doc and all(self.doc.get(key) == value for key, value in query.items()):
			return self.doc
		return None


class DB:
	def __init__(self, pipeline, run):
		self.pipelines = Collection(pipeline)
		self.pipeline_runs = Collection(run)


def setup(monkeypatch):
	
	pipeline = {
		'pipeline_id': 'p1', 
		'owner': 'alice',
		'selections': {
			'getinfo': {'run_id': 'r3'}
		}
	}
	
	run = {
		'owner': 'alice', 
		'pipeline_id': 'p1', 
		'node_id': 'getinfo',
		'run_id': 'r3', 
		'run_name': 'run003', 
		'job_id': 'j3',
		'status': 'COMPLETED', 
		'artifacts_registered_at': 'timestamp',
		'artifacts': [{
			'name': 'project_info', 
			'relative_path': 'results/project_info.json',
			'type': 'application/json', 
			'role': 'primary_result', 
			'size_bytes': 2
		}]
	}

	def get_pipeline(owner, pipeline_id):
		if owner != 'alice' or pipeline_id != 'p1':
			raise manager.PipelineError('Pipeline not found', 404)
		return pipeline

	monkeypatch.setattr(manager, 'get_pipeline', get_pipeline)

	opened = []

	def open_artifact(db, owner, run_doc, index, retention_root=None):
		assert owner == 'alice' and run_doc is run and index == 0
		f = io.BytesIO(b'{}')
		opened.append(f)
		return f, 'project_info.json', 'application/json'

	monkeypatch.setattr(resolver.access, 'open_registered_artifact', open_artifact)
	return DB(pipeline, run), pipeline, run, opened


def test_selected_unique_artifact(monkeypatch):
	db, _, _, opened = setup(monkeypatch)
	result = resolver.resolve_selected_artifact(db, 'alice', 'p1', 'getinfo', 'project_info')
	assert result['available'] is True
	assert result['run_id'] == 'r3'
	assert result['artifact']['index'] == 0
	assert 'artifact_workspace' not in result
	assert opened[0].closed


def test_no_selection(monkeypatch):
	db, pipeline, _, _ = setup(monkeypatch)
	pipeline['selections'] = {}
	with pytest.raises(manager.PipelineError) as exc:
		resolver.resolve_selected_artifact(db, 'alice', 'p1', 'getinfo', 'project_info')
	assert exc.value.status == 409


def test_wrong_owner(monkeypatch):
	db, _, _, _ = setup(monkeypatch)
	with pytest.raises(manager.PipelineError) as exc:
		resolver.resolve_selected_artifact(db, 'bob', 'p1', 'getinfo', 'project_info')
	assert exc.value.status == 404


def test_ambiguous_name(monkeypatch):
	db, _, run, _ = setup(monkeypatch)
	run['artifacts'].append(dict(run['artifacts'][0]))
	with pytest.raises(manager.PipelineError) as exc:
		resolver.resolve_selected_artifact(db, 'alice', 'p1', 'getinfo', 'project_info')
	assert exc.value.status == 409


def test_missing_artifact(monkeypatch):
	db, _, _, _ = setup(monkeypatch)
	with pytest.raises(manager.PipelineError) as exc:
		resolver.resolve_selected_artifact(db, 'alice', 'p1', 'getinfo', 'manifest')
	assert exc.value.status == 404


def test_incomplete_run(monkeypatch):
	db, _, run, _ = setup(monkeypatch)
	run['status'] = 'FAILED'
	with pytest.raises(manager.PipelineError) as exc:
		resolver.resolve_selected_artifact(db, 'alice', 'p1', 'getinfo', 'project_info')
	assert exc.value.status == 409


def test_unregistered(monkeypatch):
	db, _, run, _ = setup(monkeypatch)
	run.pop('artifacts_registered_at')
	with pytest.raises(manager.PipelineError) as exc:
		resolver.resolve_selected_artifact(db, 'alice', 'p1', 'getinfo', 'project_info')
	assert exc.value.status == 409


def test_stale_selection(monkeypatch):
	db, pipeline, _, _ = setup(monkeypatch)
	pipeline['selections']['getinfo']['run_id'] = 'unknown'
	with pytest.raises(manager.PipelineError) as exc:
		resolver.resolve_selected_artifact(db, 'alice', 'p1', 'getinfo', 'project_info')
	assert exc.value.status == 404
