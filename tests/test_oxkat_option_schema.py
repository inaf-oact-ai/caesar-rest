"""Regression tests for unified OXKAT option discovery and validation."""

import pytest

from caesar_rest.app_configurators.oxkat import OxkatAppConfigurator
from caesar_rest.app_configurators import oxkat_scientific_config


@pytest.fixture
def app():
	return OxkatAppConfigurator()


def test_legacy_job_options_preserved(app):
	description = app.describe_dict()
	assert set(description['job_options']) == {'stage'}
	assert description['job_options']['stage'] == app.valid_options['stage'].to_dict()['stage']


def test_unified_schema_interfaces(app):
	schema = app.describe_dict()['option_schema']
	assert set(schema) == {'stage', 'target', 'oxkat_config', 'preview_retention'}
	assert set(schema['stage']['interfaces']) == {'v1', 'pipeline_v2'}
	for name in ('target', 'oxkat_config', 'preview_retention'):
		assert set(schema[name]['interfaces']) == {'pipeline_v2'}


def test_published_preview_policy_matches_validator(app):
	option = app.describe_dict()['option_schema']['preview_retention']['interfaces']['pipeline_v2']
	assert option['allowed_values'] == ['none', 'selected', 'all']
	assert option['default'] == 'selected'
	assert option['stages'] == ['FLAG', '2GC']
	for stage in option['stages']:
		for profile in option['allowed_values']:
			assert app.validate_pipeline_options({'stage': stage, 'preview_retention': profile}) is None
	with pytest.raises(ValueError, match='preview_retention'):
		app.validate_pipeline_options({'stage': '1GC', 'preview_retention': 'all'})


def test_scientific_descriptions_derive_from_authoritative_registry(app):
	option = app.describe_dict()['option_schema']['oxkat_config']['interfaces']['pipeline_v2']
	assert option['type'] == 'object'
	assert option['max_properties'] == 128
	assert option['additional_properties'] is False
	properties = option['properties']
	for key, spec in oxkat_scientific_config.SCHEMA.items():
		active = [stage for stage in ('GET_INFO', '1GC', 'FLAG', '2GC') if stage in spec['stages']]
		assert (key in properties) == bool(active)
		if active:
			assert properties[key]['kind'] == spec['kind']
			assert properties[key]['stages'] == active
			if 'minimum' in spec:
				assert properties[key]['minimum'] == spec['minimum']
			if 'maximum' in spec:
				assert properties[key]['maximum'] == spec['maximum']
			if 'choices' in spec:
				assert properties[key]['choices'] == spec['choices']


def test_schema_description_is_json_serializable(app):
	import json
	json.dumps(app.describe_dict(), allow_nan=False)


@pytest.mark.parametrize('bad', ['bad', '', None, 1, [], {}])
def test_registration_validation_rejects_invalid_policy(app, bad):
	with pytest.raises(ValueError):
		app.validate_pipeline_options({'stage': 'FLAG', 'preview_retention': bad})
