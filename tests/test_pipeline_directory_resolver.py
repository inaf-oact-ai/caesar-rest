"""Unit tests for H2D-C1d1 logical retained-directory resolution."""

import pytest

from caesar_rest.pipeline.artifacts import directory_resolver as resolver
from caesar_rest.pipeline import manager


def _setup(monkeypatch):
	artifact = {
		'name': 'calibrated_ms', 'kind': 'directory',
		'relative_path': 'results/calibrated.ms',
		'size_bytes': 10, 'file_count': 2, 'directory_count': 1
	}
	record = {
		'index': 0, 'kind': 'directory', 'size_bytes': 10,
		'file_count': 2, 'directory_count': 1,
		'manifest_name': '0000.manifest.json', 'manifest_sha256': 'a' * 64
	}
	run = {
		'pipeline_id': 'p1', 'run_id': 'r1', 'run_name': 'run001',
		'job_id': 'j1', 'status': 'COMPLETED',
		'artifacts_registered_at': 'now',
		'artifacts': [artifact], 'retained_artifacts': [record]
	}
	pipeline = {'selections': {'stage1': {'run_id': 'r1'}}}
	calls = []
	def get_pipeline(owner, pipeline_id):
		if owner != 'alice':
			raise manager.PipelineError('Pipeline not found', 404)
		return pipeline
	def get_run(db, owner, pipeline_id, node_id, run_id):
		if owner != 'alice':
			raise manager.PipelineError('Run not found', 404)
		return run
	def verify(base, index, metadata, **kwargs):
		calls.append((base, index, metadata, kwargs))
		return {'verified': True}
	monkeypatch.setattr(resolver.manager, 'get_pipeline', get_pipeline)
	monkeypatch.setattr(resolver.access, 'get_run', get_run)
	monkeypatch.setattr(resolver.integrity, 'verify_directory_artifact', verify)
	return run, pipeline, calls


def _resolve(root='/tmp/retained'):
	return resolver.resolve_selected_directory(
		None, 'alice', 'p1', 'stage1', 'calibrated_ms', root
	)


def test_selected_directory_returns_logical_reference(monkeypatch):
	run, pipeline, calls = _setup(monkeypatch)
	result = _resolve()
	assert result['available'] is True
	assert result['artifact']['manifest_sha256'] == 'a' * 64
	assert result['artifact']['index'] == 0
	assert 'storage_path' not in str(result)
	assert calls[0][1] == 0


def test_missing_retention_is_rejected(monkeypatch):
	run, pipeline, calls = _setup(monkeypatch)
	run.pop('retained_artifacts')
	with pytest.raises(manager.PipelineError) as exc:
		_resolve()
	assert exc.value.status == 409
	assert not calls


def test_ambiguous_artifact_is_rejected(monkeypatch):
	run, pipeline, calls = _setup(monkeypatch)
	run['artifacts'].append(dict(run['artifacts'][0]))
	with pytest.raises(manager.PipelineError) as exc:
		_resolve()
	assert exc.value.status == 409


def test_selected_file_is_rejected(monkeypatch):
	run, pipeline, calls = _setup(monkeypatch)
	run['artifacts'][0]['kind'] = 'file'
	with pytest.raises(manager.PipelineError) as exc:
		_resolve()
	assert exc.value.status == 409


def test_wrong_owner_is_rejected(monkeypatch):
	_setup(monkeypatch)
	with pytest.raises(manager.PipelineError) as exc:
		resolver.resolve_selected_directory(None, 'bob', 'p1', 'stage1', 'calibrated_ms', '/tmp/retained')
	assert exc.value.status == 404


def test_failed_integrity_is_rejected(monkeypatch):
	from caesar_rest.pipeline.artifacts.directory_integrity import DirectoryIntegrityError
	_setup(monkeypatch)
	def fail(*args, **kwargs):
		raise DirectoryIntegrityError('corrupted')
	monkeypatch.setattr(resolver.integrity, 'verify_directory_artifact', fail)
	with pytest.raises(manager.PipelineError) as exc:
		_resolve()
	assert exc.value.status == 409
	assert 'corrupted' not in str(exc.value)


def test_selection_frozen_at_lookup(monkeypatch):
	run, pipeline, calls = _setup(monkeypatch)
	pipeline['selections'] = {}
	with pytest.raises(manager.PipelineError) as exc:
		_resolve()
	assert exc.value.status == 409
