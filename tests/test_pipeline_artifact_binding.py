"""Metadata-only upstream bindings; isolated DB and storage mocks."""
import hashlib
from types import SimpleNamespace

import pytest

from caesar_rest.pipeline.artifacts import binding
from caesar_rest.pipeline import manager


class Runs:
	def __init__(self, run):
		self.run = run

	def find_one(self, query):
		if query['owner'] == 'alice' and query['pipeline_id'] == 'p1' and query['run_id'] == 'r1' and query['status'] == 'COMPLETED':
			return self.run
		return None


def make_db(kind='directory'):
	sha = hashlib.sha256(b'{}').hexdigest()
	record = {'index': 0, 'size_bytes': 2}
	artifact = {'name': 'output', 'relative_path': 'results/output.ms' if kind == 'directory' else 'results/output.json', 'size_bytes': 2}
	if kind == 'directory':
		artifact.update({'kind': 'directory', 'file_count': 1, 'directory_count': 0})
		record.update({'kind': 'directory', 'manifest_sha256': sha, 'manifest_name': '0000.manifest.json', 'file_count': 1, 'directory_count': 0})
	else:
		record['sha256'] = sha
	run = {'node_id': 'stage1', 'run_id': 'r1', 'status': 'COMPLETED', 'artifacts_registered_at': 'now', 'artifacts': [artifact], 'retained_artifacts': [record]}
	return SimpleNamespace(pipeline_runs=Runs(run)), run


def request():
	return [{'input_name': 'calibrated_ms', 'source_run_id': 'r1', 'artifact_index': 0}]


def test_directory_binding_freezes_identity(monkeypatch):
	db, run = make_db()
	monkeypatch.setattr(
		binding.integrity,
		'verify_directory_manifest',
		lambda *args, **kwargs: {'verified': True}
	)
	
	result = binding.bind_inputs(db, 'alice', 'p1', request(), '/tmp/artifacts')
	assert result[0]['source_run_id'] == 'r1'
	assert result[0]['source_node_id'] == 'stage1'
	assert result[0]['manifest_sha256'] == run['retained_artifacts'][0]['manifest_sha256']
	assert 'relative_path' not in result[0]
	assert 'storage_path' not in result[0]


def test_wrong_owner_rejected():
	db, _ = make_db()
	with pytest.raises(manager.PipelineError):
		binding.bind_inputs(db, 'bob', 'p1', request(), '/tmp/artifacts')


def test_duplicate_input_names_rejected(monkeypatch):
	db, _ = make_db()
	with pytest.raises(manager.PipelineError):
		binding.bind_inputs(db, 'alice', 'p1', request() * 2, '/tmp/artifacts')


def test_missing_retention_rejected():
	db, run = make_db()
	run.pop('retained_artifacts')
	with pytest.raises(manager.PipelineError):
		binding.bind_inputs(db, 'alice', 'p1', request(), '/tmp/artifacts')


def test_directory_integrity_failure_rejected(monkeypatch):
	db, _ = make_db()
	def fail(*args, **kwargs):
		raise binding.integrity.DirectoryIntegrityError('bad')
	#monkeypatch.setattr(binding.integrity, 'verify_directory_artifact', fail)
	monkeypatch.setattr(binding.integrity, 'verify_directory_manifest', fail)
		
	with pytest.raises(manager.PipelineError):
		binding.bind_inputs(db, 'alice', 'p1', request(), '/tmp/artifacts')


def test_file_binding_uses_verified_retained_copy(monkeypatch):
	import io
	db, _ = make_db('file')
	monkeypatch.setattr(binding.access, 'open_registered_artifact', lambda *args, **kwargs: (io.BytesIO(b'{}'), 'output.json', 'application/json'))
	result = binding.bind_inputs(db, 'alice', 'p1', request(), '/tmp/artifacts')
	assert result[0]['artifact_kind'] == 'file'
	assert result[0]['sha256'] == hashlib.sha256(b'{}').hexdigest()
