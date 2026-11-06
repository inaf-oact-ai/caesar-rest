
"""Tests for explicit-run and selected-run artifact file lookup."""

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


@pytest.fixture
def fixture(monkeypatch):
	pipeline = {
		'pipeline_id': 'pipe1', 'owner': 'alice',
		'selections': {'stage_2gc': {'run_id': 'run1'}}
	}
	run = {
		'owner': 'alice', 'pipeline_id': 'pipe1',
		'node_id': 'stage_2gc', 'run_id': 'run1',
		'run_name': 'run001', 'job_id': 'job1',
		'status': 'COMPLETED', 'artifacts_registered_at': 'now',
		'artifacts': [
			{'name': 'image_qa', 'relative_path': 'results/previews/image_qa.json',
				'size_bytes': 2, 'type': 'application/json'},
			{'name': 'image_previews', 'relative_path': 'results/previews/selected/a.png',
				'size_bytes': 1, 'type': 'image/png'},
			{'name': 'image_previews', 'relative_path': 'results/previews/selected/b.png',
				'size_bytes': 1, 'type': 'image/png'}
		]
	}
	opened = []

	def open_file(db, owner, doc, index, retention_root=None):
		assert owner == 'alice' and doc is run
		fileobj = io.BytesIO(b'{}')
		opened.append((index, fileobj))
		return fileobj, 'file.json', 'application/json'

	monkeypatch.setattr(resolver.access, 'open_registered_artifact', open_file)
	return DB(pipeline, run), pipeline, run, opened


def test_explicit_run_needs_no_selection(fixture):
	db, pipeline, run, opened = fixture
	pipeline['selections'] = {}
	stream, _, _ = resolver.open_run_artifact(
		db, 'alice', 'pipe1', 'stage_2gc', 'run1', artifact_name='image_qa')
	assert opened[0][0] == 0
	stream.close()


def test_selected_alias(fixture):
	db, _, _, opened = fixture
	result = resolver.resolve_run_artifact(
		db, 'alice', 'pipe1', 'stage_2gc', 'selected', artifact_name='image_qa')
	assert result['run_id'] == 'run1'
	assert result['artifact']['index'] == 0
	assert opened[0][1].closed


def test_selected_without_selection(fixture):
	db, pipeline, _, _ = fixture
	pipeline['selections'] = {}
	with pytest.raises(manager.PipelineError) as exc:
		resolver.open_run_artifact(
			db, 'alice', 'pipe1', 'stage_2gc', 'selected', artifact_name='image_qa')
	assert exc.value.status == 409


def test_ambiguous_name(fixture):
	db, _, _, _ = fixture
	with pytest.raises(manager.PipelineError) as exc:
		resolver.open_run_artifact(
			db, 'alice', 'pipe1', 'stage_2gc', 'run1', artifact_name='image_previews')
	assert exc.value.status == 409


def test_exact_path_selects_one_preview(fixture):
	db, _, _, opened = fixture
	stream, _, _ = resolver.open_run_artifact(
		db, 'alice', 'pipe1', 'stage_2gc', 'run1',
		relative_path='results/previews/selected/b.png')
	assert opened[0][0] == 2
	stream.close()


@pytest.mark.parametrize('path', [
	'../../etc/passwd', '/etc/passwd', 'results/../secret',
	'results//a', 'results/other\\file', 'results/./a'
])
def test_reject_unsafe_paths(fixture, path):
	db, _, _, _ = fixture
	with pytest.raises(manager.PipelineError) as exc:
		resolver.open_run_artifact(
			db, 'alice', 'pipe1', 'stage_2gc', 'run1', relative_path=path)
	assert exc.value.status == 400


def test_wrong_owner(fixture):
	db, _, _, _ = fixture
	with pytest.raises(manager.PipelineError) as exc:
		resolver.open_run_artifact(
			db, 'bob', 'pipe1', 'stage_2gc', 'run1', artifact_name='image_qa')
	assert exc.value.status == 404


def test_unregistered_and_incomplete_run(fixture):
	db, _, run, _ = fixture
	run['status'] = 'RUNNING'
	with pytest.raises(manager.PipelineError) as exc:
		resolver.open_run_artifact(db, 'alice', 'pipe1', 'stage_2gc', 'run1', artifact_name='image_qa')
	assert exc.value.status == 409
	run['status'] = 'COMPLETED'
	run.pop('artifacts_registered_at')
	with pytest.raises(manager.PipelineError) as exc:
		resolver.open_run_artifact(db, 'alice', 'pipe1', 'stage_2gc', 'run1', artifact_name='image_qa')
	assert exc.value.status == 409


def test_legacy_selected_resolver_still_works(fixture):
	db, _, _, _ = fixture
	result = resolver.resolve_selected_artifact(db, 'alice', 'pipe1', 'stage_2gc', 'image_qa')
	assert result['artifact']['index'] == 0

