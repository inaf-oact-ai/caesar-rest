"""Lightweight MAASAI orchestration contract checks.

Run from repository root: python -m pytest -q tests/test_maasai_contract.py
Checks public routing and important bulk request semantics; no DB/Slurm.
"""

import pytest
from flask import Flask

from caesar_rest.pipeline import bulk_registration, bulk_planning, manager
from caesar_rest.pipeline.routes import pipeline_bp


def test_public_routes_available():
	app = Flask(__name__)
	app.register_blueprint(pipeline_bp)
	routes = {(rule.rule, method) for rule in app.url_map.iter_rules()
		for method in rule.methods}
	prefix = '/caesar/api/v1.0/pipelines/<pipeline_id>'
	for method, suffix in (
		('GET', '/readiness'),
		('GET', '/scientific-readiness'),
		('GET', '/tree'),
		('POST', '/bulk-plan'),
		('POST', '/bulk-register'),
		('POST', '/runs'),
		('POST', '/runs/<run_id>/submit'),
		('PUT', '/nodes/<node_id>/selection'),
	):
		assert (prefix + suffix, method) in routes


def test_bulk_registration_rejects_missing_key():
	with pytest.raises(manager.PipelineError) as exc:
		bulk_registration.validate_request({'items': [{'registration': {
			'stage': 'FLAG', 'node_id': 'stage_flag_f1',
			'parameters': {'target': 'MAXIJ1348'}, 'inputs': {}
		}}]})
	assert exc.value.status == 400


def test_bulk_registration_rejects_duplicate_target():
	registration = {'stage': 'FLAG', 'node_id': 'stage_flag_f1',
		'parameters': {'target': 'MAXIJ1348'}, 'inputs': {}}
	with pytest.raises(manager.PipelineError) as exc:
		bulk_registration.validate_request({'items': [
			{'idempotency_key': 'key1', 'registration': registration},
			{'idempotency_key': 'key2', 'registration': registration}
		]})
	assert exc.value.status == 400


def test_bulk_plan_rejects_duplicate_target_filter():
	with pytest.raises(manager.PipelineError) as exc:
		bulk_planning.validate_request({'stage': 'FLAG',
			'targets': ['MAXIJ1348', 'MAXIJ1348']})
	assert exc.value.status == 400


def test_bulk_registration_requires_nonempty_list():
	with pytest.raises(manager.PipelineError) as exc:
		bulk_registration.validate_request({'items': []})
	assert exc.value.status == 400
