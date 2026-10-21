
import pytest

from caesar_rest.job_configurator import JobConfigurator
from caesar_rest.pipeline.staging.submission_specs import (
	create_specs,
	PipelineSubmissionError,
)


def make_specs(input_mode='copy'):
	inputfile = '/data/observation.ms'

	return create_specs(
		workspace_app='/jobs/job_test',
		workspace_cluster='/cluster/jobs/job_test',
		inputfile=inputfile,
		cmd_arg_list=[
			'--stage=GET_INFO',
			'--input-ms=' + inputfile,
		],
		image='/containers/oxkat.sif',
		app_data_root='/data',
		cluster_data_root='/cluster/data',
		app_job_root='/jobs',
		cluster_job_root='/cluster/jobs',
		input_mode=input_mode,
	)


def test_reference_staging_spec():
	staging, execution = make_specs('reference_ro')

	entry = staging['inputs'][0]

	assert entry['mode'] == 'reference_ro'
	assert entry['writable'] is False
	assert entry['source'] == '/cluster/data/observation.ms'

	assert execution['input_options'] == {
		'input-ms': 'observation.ms'
	}


def test_copy_staging_remains_default():
	staging, execution = make_specs()

	entry = staging['inputs'][0]

	assert entry['mode'] == 'copy'
	assert entry['writable'] is True


def test_invalid_staging_mode_rejected():
	with pytest.raises(PipelineSubmissionError):
		make_specs('invalid_mode')


def test_generic_reference_has_no_oxkat_dependency():
	"""The generic resolver must support other applications too."""

	inputfile = '/data/scientific_dataset'

	staging, execution = create_specs(
		workspace_app='/jobs/job_test',
		workspace_cluster='/cluster/jobs/job_test',
		inputfile=inputfile,
		cmd_arg_list=[
			'--analyze',
			'--input-dir=' + inputfile,
		],
		image='/containers/generic.sif',
		app_data_root='/data',
		cluster_data_root='/cluster/data',
		app_job_root='/jobs',
		cluster_job_root='/cluster/jobs',
		input_mode='reference_ro',
	)

	assert staging['inputs'][0]['mode'] == 'reference_ro'
	assert staging['inputs'][0]['writable'] is False
	assert execution['input_options'] == {
		'input-dir': 'scientific_dataset'
	}


def test_oxkat_configurator_selects_reference():
	jobcfg = JobConfigurator()

	inputfile = '/data/observation.ms'

	cmd, args, status, run_opts = jobcfg.validate(
		'oxkat',
		{'stage': 'GET_INFO'},
		inputfile
	)

	assert cmd is not None
	assert args is not None
	assert '--input-ms=' + inputfile in args

	assert run_opts['input_staging_mode'] == 'reference_ro'


def test_oxkat_rejects_unimplemented_stage():
	jobcfg = JobConfigurator()

	cmd, args, status, run_opts = jobcfg.validate(
		'oxkat',
		{'stage': '1GC'},
		'/data/observation.ms'
	)

	assert cmd is None
	assert args is None
	assert run_opts is None


def test_client_cannot_select_staging_strategy():
	"""An arbitrary client option must not override server policy."""

	jobcfg = JobConfigurator()

	cmd, args, status, run_opts = jobcfg.validate(
		'oxkat',
		{
			'stage': 'GET_INFO',
			'input_staging_mode': 'copy',
		},
		'/data/observation.ms'
	)

	# The extra option should fail normal application validation.
	assert cmd is None
	assert args is None
	assert run_opts is None

