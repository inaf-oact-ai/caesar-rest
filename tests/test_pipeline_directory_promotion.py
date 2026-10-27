import hashlib
from types import SimpleNamespace

import pytest

from caesar_rest.pipeline.artifacts import access
from caesar_rest.pipeline.artifacts import directory_promotion as promotion
from caesar_rest.pipeline import manager


class Runs:
	def __init__(self, run):
		self.run = run

	def update_one(self, query, changes):
		if 'retained_artifacts' in self.run:
			return SimpleNamespace(modified_count=0)
		self.run.update(changes['$set'])
		return SimpleNamespace(modified_count=1)


class DB:
	def __init__(self, run):
		self.pipeline_runs = Runs(run)


def example_run():
	return {
		'owner': 'alice', 'pipeline_id': 'pipe1', 'node_id': 'getinfo',
		'run_id': 'run1', 'status': 'COMPLETED',
		'artifacts_registered_at': 'now',
		'artifacts': [
			{'name': 'manifest', 'kind': 'file', 'size_bytes': 2,
				'relative_path': 'results/manifest.json'},
			{'name': 'ms', 'kind': 'directory', 'size_bytes': 5,
				'file_count': 1, 'directory_count': 0,
				'relative_path': 'results/calibrated.ms'}
		]
	}


def test_mixed_run_records_compact_manifest(tmp_path, monkeypatch):
	run = example_run()
	db = DB(run)
	monkeypatch.setattr(access, 'get_run', lambda *args: run)
	import io
	monkeypatch.setattr(access, 'open_registered_artifact',
		lambda *args: (io.BytesIO(b'{}'), 'manifest.json', 'application/json'))
	source = tmp_path / 'source.ms'
	source.mkdir()
	(source / 'table.dat').write_bytes(b'hello')
	monkeypatch.setattr(promotion, '_source_directory', lambda *args: str(source))
	root = str(tmp_path / 'store')
	response = promotion.promote_mixed_run(db, 'alice', 'pipe1', 'getinfo', 'run1',
		root, 1000, 1000, 100, 5)
	assert response['count'] == 2
	base = tmp_path / 'store' / 'alice' / 'pipe1' / 'run1'
	assert (base / '0000').read_bytes() == b'{}'
	assert (base / '0001' / 'table.dat').read_bytes() == b'hello'
	assert (base / '0001.manifest.json').exists()
	assert 'manifest' not in run['retained_artifacts'][1]
	assert run['retained_artifacts'][1]['manifest_sha256'] == hashlib.sha256(
		(base / '0001.manifest.json').read_bytes()).hexdigest()
	assert promotion.promote_mixed_run(db, 'alice', 'pipe1', 'getinfo', 'run1',
		root, 1000, 1000, 100, 5)['already_retained']


def test_missing_discovery_metadata_does_not_publish(tmp_path, monkeypatch):
	run = example_run()
	run['artifacts'][1]['file_count'] = 2
	db = DB(run)
	monkeypatch.setattr(access, 'get_run', lambda *args: run)
	import io
	monkeypatch.setattr(access, 'open_registered_artifact',
		lambda *args: (io.BytesIO(b'{}'), 'manifest.json', 'application/json'))
	source = tmp_path / 'source.ms'
	source.mkdir()
	(source / 'table.dat').write_bytes(b'hello')
	monkeypatch.setattr(promotion, '_source_directory', lambda *args: str(source))
	with pytest.raises(manager.PipelineError):
		promotion.promote_mixed_run(db, 'alice', 'pipe1', 'getinfo', 'run1',
			str(tmp_path / 'store'), 1000, 1000, 100, 5)
	assert 'retained_artifacts' not in run
