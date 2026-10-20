"""Tests for frozen-reference staging without Slurm or a real database."""
import hashlib
import io
import os
from types import SimpleNamespace

import pytest

from caesar_rest.pipeline.staging import bound as staging
from caesar_rest.pipeline import manager


class Runs:
	def __init__(self, source):
		self.source = source

	def find_one(self, query):
		if query['owner'] != 'alice' or query['run_id'] != 'r1':
			return None
		return self.source


def setup(monkeypatch, tmp_path):
	workspace = tmp_path / 'job'
	workspace.mkdir(mode=0o700)
	data = b'verified result'
	sha = hashlib.sha256(data).hexdigest()
	source = {'node_id': 'calibration', 'pipeline_id': 'p1', 'run_id': 'r1',
		'status': 'COMPLETED', 'artifacts_registered_at': 'now',
		'artifacts': [{'name': 'result', 'relative_path': 'results/result.dat',
			'size_bytes': len(data)}],
		'retained_artifacts': [{'index': 0, 'size_bytes': len(data), 'sha256': sha}]}
	bound = {'input_name': 'science_input', 'source_pipeline_id': 'p1',
		'source_node_id': 'calibration', 'source_run_id': 'r1',
		'artifact_index': 0, 'artifact_name': 'result', 'artifact_kind': 'file',
		'size_bytes': len(data), 'sha256': sha}
	downstream = {'pipeline_id': 'p1', 'input_runs': ['r1'], 'input_artifacts': [bound]}
	monkeypatch.setattr(staging.retention, 'open_retained_artifact',
		lambda *args, **kwargs: (io.BytesIO(data), 'result.dat', 'application/octet-stream'))
	return SimpleNamespace(pipeline_runs=Runs(source)), downstream, workspace, data


def test_stages_frozen_file(monkeypatch, tmp_path):
	db, run, workspace, data = setup(monkeypatch, tmp_path)
	result = staging.stage_bound_inputs(db, 'alice', run, str(tmp_path / 'retained'), str(workspace))
	assert len(result) == 1
	assert (workspace / 'inputs' / 'science_input').read_bytes() == data
	assert result[0]['source_run_id'] == 'r1'
	assert oct(os.stat(workspace / 'inputs' / 'science_input').st_mode & 0o777) == '0o600'


def test_rejects_mutated_frozen_digest_before_copy(monkeypatch, tmp_path):
	db, run, workspace, _ = setup(monkeypatch, tmp_path)
	run['input_artifacts'][0]['sha256'] = '0' * 64
	with pytest.raises(manager.PipelineError):
		staging.stage_bound_inputs(db, 'alice', run, str(tmp_path / 'retained'), str(workspace))
	assert not (workspace / 'inputs' / 'science_input').exists()


def test_refuses_existing_staging_directory(monkeypatch, tmp_path):
	db, run, workspace, _ = setup(monkeypatch, tmp_path)
	(workspace / 'inputs').mkdir()
	with pytest.raises(manager.PipelineError):
		staging.stage_bound_inputs(db, 'alice', run, str(tmp_path / 'retained'), str(workspace))


def test_rejects_other_pipeline_reference(monkeypatch, tmp_path):
	db, run, workspace, _ = setup(monkeypatch, tmp_path)
	run['input_artifacts'][0]['source_pipeline_id'] = 'p2'
	with pytest.raises(manager.PipelineError):
		staging.stage_bound_inputs(db, 'alice', run, str(tmp_path / 'retained'), str(workspace))
