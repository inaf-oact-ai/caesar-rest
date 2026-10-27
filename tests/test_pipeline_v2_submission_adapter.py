"""Metadata-level tests: no Slurm or worker execution."""
import copy
from types import SimpleNamespace

import pytest

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.submission import v2_adapter as adapter


@pytest.fixture
def sample(monkeypatch, tmp_path):
	base = tmp_path / 'retained'
	directory = base / 'alice' / 'p1' / 'r1'
	directory.mkdir(parents=True)
	(directory / '0000').write_bytes(b'data')
	stored = [{'input_name': 'vis', 'source_pipeline_id': 'p1',
		'source_node_id': 'stage1', 'source_run_id': 'r1',
		'artifact_index': 0, 'artifact_name': 'output',
		'artifact_kind': 'file', 'size_bytes': 4, 'sha256': 'a' * 64}]
	run = {'owner': 'alice', 'pipeline_id': 'p1', 'node_id': 'stage2',
		'run_id': 'r2', 'status': 'PLANNED', 'input_runs': ['r1'],
		'input_artifacts': stored}
	monkeypatch.setattr(adapter.manager, 'get_pipeline', lambda *args: {'pipeline_id': 'p1'})
	monkeypatch.setattr(adapter.binding, 'bind_inputs', lambda *args, **kwargs: copy.deepcopy(stored))
	return run, str(base)


def invoke(run, root):
	return adapter.build_bound_v2_specs(SimpleNamespace(), 'alice', run, root,
		'/cluster/retained', '/cluster/jobs/job_123', '/images/science.sif',
		['--run'], {'ms': 'vis'})


def test_builds_trusted_v2_specs(sample):
	run, root = sample
	stage, execution = invoke(run, root)
	assert stage['version'] == execution['version'] == 2
	assert stage['inputs'][0]['source'] == '/cluster/retained/alice/p1/r1/0000'
	assert execution['input_options'] == {'ms': 'vis'}


def test_frozen_checksum_change_rejected(sample, monkeypatch):
	run, root = sample
	changed = copy.deepcopy(run['input_artifacts'])
	changed[0]['sha256'] = 'b' * 64
	monkeypatch.setattr(adapter.binding, 'bind_inputs', lambda *args, **kwargs: changed)
	with pytest.raises(manager.PipelineError):
		invoke(run, root)


def test_other_owner_rejected(sample):
	run, root = sample
	run['owner'] = 'mallory'
	with pytest.raises(manager.PipelineError):
		invoke(run, root)


def test_changed_status_rejected(sample):
	run, root = sample
	run['status'] = 'SUBMITTED'
	with pytest.raises(manager.PipelineError):
		invoke(run, root)


def test_unlisted_parent_rejected(sample):
	run, root = sample
	run['input_runs'] = []
	with pytest.raises(manager.PipelineError):
		invoke(run, root)


def test_symlinked_retention_directory_rejected(sample, tmp_path):
	run, root = sample
	import os
	os.unlink(os.path.join(root, 'alice', 'p1', 'r1', '0000'))
	os.rmdir(os.path.join(root, 'alice', 'p1', 'r1'))
	os.symlink(str(tmp_path), os.path.join(root, 'alice', 'p1', 'r1'))
	with pytest.raises(manager.PipelineError):
		invoke(run, root)
