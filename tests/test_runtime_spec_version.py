"""H2C2b1 compatibility and v2 runtime tests (no Slurm required)."""
import json

import pytest

from caesar_pipeline_runtime.version import specification_version
from caesar_pipeline_runtime.staging import stage_inputs, StagingError
from caesar_pipeline_runtime.stage_runner import prepare
from caesar_pipeline_runtime.executor import _validated_spec, ContainerExecutionError


def test_missing_version_is_v1():
	assert specification_version({'inputs': []}) == 1
	assert specification_version({'version': 1}) == 1
	assert specification_version({'version': 2}) == 2


@pytest.mark.parametrize('bad', [None, True, False, '1', '2', 0, 3, 2.0, [], {}])
def test_invalid_version_rejected(bad):
	with pytest.raises(ValueError):
		specification_version({'version': bad})


def test_v1_stage_runner_without_version(tmp_path):
	source = tmp_path / 'source.json'
	source.write_text('{}')
	ws = tmp_path / 'workspace'
	ws.mkdir()
	spec = ws / 'staging_spec.json'
	spec.write_text(json.dumps({'inputs': [{'source': str(source), 'name': 'data', 'mode': 'copy', 'writable': True}]}))
	assert prepare(str(spec), str(ws))['staging_state'] == 'READY'


def test_v2_multiple_inputs(tmp_path):
	file_source = tmp_path / 'data.json'
	file_source.write_bytes(b'{}')
	dir_source = tmp_path / 'calibrated.ms'
	dir_source.mkdir()
	(dir_source / 'table.dat').write_bytes(b'table')
	ws = tmp_path / 'workspace'
	ws.mkdir()
	spec = ws / 'staging_spec.json'
	spec.write_text(json.dumps({'version': 2, 'inputs': [
		{'source': str(file_source), 'name': 'settings', 'kind': 'file', 'size_bytes': 2, 'mode': 'copy', 'writable': True},
		{'source': str(dir_source), 'name': 'vis', 'kind': 'directory', 'size_bytes': 5, 'mode': 'copy', 'writable': True}
	]}))
	manifest = prepare(str(spec), str(ws))
	assert [x['name'] for x in manifest['inputs']] == ['settings', 'vis']
	assert (ws / 'input' / 'vis' / 'table.dat').read_bytes() == b'table'


def test_v2_wrong_size_does_not_publish_ready(tmp_path):
	source = tmp_path / 'data.bin'
	source.write_bytes(b'ab')
	ws = tmp_path / 'workspace'
	ws.mkdir()
	with pytest.raises(StagingError):
		stage_inputs([{'source': str(source), 'name': 'data', 'kind': 'file', 'size_bytes': 3}], str(ws))
	assert not (ws / 'input' / 'staging.json').exists()


def test_execution_v1_default_and_v2(tmp_path):
	base = {'image': '/images/x.sif', 'container_workspace': '/container/workspace',
		'arguments': ['--run'], 'input_options': {'ms': 'vis'},
		'execution_dir': 'execution', 'output_dir': 'results', 'environment': {}}
	assert _validated_spec(dict(base), str(tmp_path))[0] == '/images/x.sif'
	assert _validated_spec(dict(base, version=2), str(tmp_path))[0] == '/images/x.sif'
	with pytest.raises(ContainerExecutionError):
		_validated_spec(dict(base, version='2'), str(tmp_path))
