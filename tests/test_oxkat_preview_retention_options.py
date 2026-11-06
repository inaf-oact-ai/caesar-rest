
"""Regression tests for OXKAT preview retention options.

Tests the Pipeline V2 application-specific configuration contract.

No MongoDB, Slurm, Singularity or scientific execution is required.
"""

import pytest

from caesar_rest.app_configurators.oxkat import (
	OxkatAppConfigurator,
)


PROFILES = ('none', 'selected', 'all')
IMAGING_STAGES = ('FLAG', '2GC')


def make_configurator():
	return OxkatAppConfigurator()


def scalar_validator(parameters, allowed):
	"""Simulate generic Pipeline V2 scalar validation."""

	assert isinstance(parameters, dict)
	assert isinstance(allowed, dict)

	assert set(parameters) == set(allowed)

	args = []

	for name in sorted(allowed):
		value = parameters[name]

		assert value in allowed[name]

		args.append('--%s=%s' % (name, value))

	return args


@pytest.mark.parametrize('stage', IMAGING_STAGES)
@pytest.mark.parametrize('profile', PROFILES)
def test_accepts_valid_preview_retention(stage, profile):
	configurator = make_configurator()

	parameters = {
		'stage': stage,
		'preview_retention': profile,
	}

	assert configurator.validate_pipeline_options(
		parameters
	) is None


@pytest.mark.parametrize(
	'profile',
	[
		'invalid',
		'',
		'ALL',
		'Selected',
		None,
		True,
		False,
		0,
		1,
		[],
		{},
	]
)
def test_rejects_invalid_preview_retention(profile):
	configurator = make_configurator()

	parameters = {
		'stage': 'FLAG',
		'preview_retention': profile,
	}

	with pytest.raises(ValueError, match='preview_retention'):
		configurator.validate_pipeline_options(parameters)


@pytest.mark.parametrize('stage', ('GET_INFO', '1GC'))
@pytest.mark.parametrize('profile', PROFILES)
def test_rejects_preview_retention_for_non_imaging_stages(
	stage,
	profile
):
	configurator = make_configurator()

	parameters = {
		'stage': stage,
		'preview_retention': profile,
	}

	with pytest.raises(ValueError, match='preview_retention'):
		configurator.validate_pipeline_options(parameters)


@pytest.mark.parametrize('stage', IMAGING_STAGES)
def test_preview_retention_is_optional(stage):
	configurator = make_configurator()

	assert configurator.validate_pipeline_options({
		'stage': stage,
	}) is None


@pytest.mark.parametrize('stage', IMAGING_STAGES)
@pytest.mark.parametrize('profile', PROFILES)
def test_preview_retention_argument_translation(stage, profile):
	configurator = make_configurator()

	parameters = {
		'stage': stage,
		'preview_retention': profile,
	}

	allowed = {
		'stage': [stage],
	}

	args = configurator.build_pipeline_arguments(
		parameters,
		allowed,
		scalar_validator,
	)

	assert args == [
		'--stage=%s' % stage,
		'--preview-retention=%s' % profile,
	]


@pytest.mark.parametrize('stage', IMAGING_STAGES)
def test_default_argument_does_not_add_retention_override(stage):
	configurator = make_configurator()

	parameters = {
		'stage': stage,
	}

	allowed = {
		'stage': [stage],
	}

	args = configurator.build_pipeline_arguments(
		parameters,
		allowed,
		scalar_validator,
	)

	assert args == [
		'--stage=%s' % stage,
	]

	assert not any(
		arg.startswith('--preview-retention=')
		for arg in args
	)


@pytest.mark.parametrize('profile', PROFILES)
def test_preview_retention_with_target(profile):
	configurator = make_configurator()

	parameters = {
		'stage': 'FLAG',
		'target': 'TARGET_A',
		'preview_retention': profile,
	}

	allowed = {
		'stage': ['FLAG'],
	}

	args = configurator.build_pipeline_arguments(
		parameters,
		allowed,
		scalar_validator,
	)

	assert '--stage=FLAG' in args
	assert '--target-name=TARGET_A' in args
	assert '--preview-retention=%s' % profile in args


@pytest.mark.parametrize('profile', PROFILES)
def test_preview_retention_with_scientific_overrides(profile):
	configurator = make_configurator()

	parameters = {
		'stage': 'FLAG',
		'preview_retention': profile,
		'oxkat_config': {
			'WSC_NITER': 7500000,
		},
	}

	allowed = {
		'stage': ['FLAG'],
	}

	args = configurator.build_pipeline_arguments(
		parameters,
		allowed,
		scalar_validator,
	)

	assert '--stage=FLAG' in args
	assert '--preview-retention=%s' % profile in args

	# Scientific overrides must remain encoded separately.
	config_args = [
		arg
		for arg in args
		if arg.startswith('--oxkat-config=')
	]

	assert len(config_args) == 1

	# Preview retention is an execution/publication policy,
	# not a WSClean scientific configuration override.
	assert not any(
		'preview_retention' in arg
		for arg in config_args
	)


def test_rejects_unknown_preview_option():
	configurator = make_configurator()

	with pytest.raises(ValueError, match='Unsupported OXKAT job options'):
		configurator.validate_pipeline_options({
			'stage': 'FLAG',
			'preview_profile': 'all',
		})


def test_legacy_valid_options_remain_unchanged():
	configurator = make_configurator()

	assert 'stage' in configurator.valid_options
	assert 'preview_retention' not in configurator.valid_options
	assert 'oxkat_config' not in configurator.valid_options
	assert 'target' not in configurator.valid_options

