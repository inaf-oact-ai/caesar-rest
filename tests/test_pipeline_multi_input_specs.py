import copy
import pytest
from caesar_rest.pipeline.staging.multi_input_specs import (
	MultiInputSpecError, build_multi_input_specs, validate_multi_input_pair
)


def _specs():
	return build_multi_input_specs(
		'/jobs/job_123',
		[
			{
				'input_name': 'vis',
				'source': '/retained/alice/p1/r1/0001',
				'kind': 'directory',
				'size_bytes': 123,
				'manifest_entries': [
					{
						'path': 'table.dat',
						'kind': 'file',
						'size_bytes': 123,
						'sha256': 'a' * 64
					}
				]
			},
			{
				'input_name': 'settings',
				'source': '/retained/alice/p1/r1/0000',
				'kind': 'file',
				'size_bytes': 9,
				'sha256': 'b' * 64
			}
		],
		'/images/oxkat.sif',
		['--run', '--model=default'],
		{'ms': 'vis', 'config': 'settings'}
	)

def test_v2_pair_carries_multiple_named_inputs():
	staging, execution = _specs()
	assert staging['version'] == execution['version'] == 2
	assert [x['kind'] for x in staging['inputs']] == ['directory', 'file']
	assert execution['input_options'] == {'ms': 'vis', 'config': 'settings'}
	assert validate_multi_input_pair(staging, execution)


def test_reject_workspace_overlap():
	with pytest.raises(MultiInputSpecError):
		build_multi_input_specs('/jobs/job_123', [{'input_name': 'vis', 'source': '/jobs/job_123/inputs/ms', 'kind': 'directory', 'size_bytes': 3}], '/images/a.sif', ['--run'], {'ms': 'vis'})


def test_reject_missing_mapping():
	staging, execution = _specs()
	with pytest.raises(MultiInputSpecError):
		build_multi_input_specs('/jobs/job_123', [{'input_name': x['name'], 'source': x['source'], 'kind': x['kind'], 'size_bytes': x['size_bytes']} for x in staging['inputs']], '/images/oxkat.sif', ['--run'], {'ms': 'vis'})


def test_reject_extra_fields_or_modified_mode():
	staging, execution = _specs()
	changed = copy.deepcopy(staging)
	changed['inputs'][0]['mode'] = 'link'
	with pytest.raises(MultiInputSpecError):
		validate_multi_input_pair(changed, execution)


def test_reject_argument_option_collision():
	with pytest.raises(MultiInputSpecError):
		build_multi_input_specs('/jobs/job_123', [{'input_name': 'vis', 'source': '/retained/r1/0001', 'kind': 'directory', 'size_bytes': 1}], '/images/a.sif', ['--ms=/some/path'], {'ms': 'vis'})


def test_reject_duplicate_names():
	with pytest.raises(MultiInputSpecError):
		build_multi_input_specs('/jobs/job_123', [{'input_name': 'vis', 'source': '/a/1', 'kind': 'file', 'size_bytes': 1}, {'input_name': 'vis', 'source': '/a/2', 'kind': 'file', 'size_bytes': 2}], '/images/a.sif', ['--run'], {'ms': 'vis'})
