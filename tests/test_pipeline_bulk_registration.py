
"""Unit tests for controlled bulk-registration orchestration."""

import pytest

from caesar_rest.pipeline import bulk_registration
from caesar_rest.pipeline import idempotency
from caesar_rest.pipeline import manager


def registration(target='TARGET_A', field_id=1):
	return {
		'stage': 'FLAG',
		'node_id': 'stage_flag_f%d' % field_id,
		'parameters': {
			'target': target
		},
		'inputs': {
			'target_ms': {
				'run_id': 'gc1',
				'artifact': 'working_measurement_sets',
				'artifact_index': field_id
			}
		}
	}


def item(key, target='TARGET_A', field_id=1):
	return {
		'idempotency_key': key,
		'registration': registration(target, field_id)
	}


def setup_fakes(monkeypatch):
	created = []
	existing = {}

	monkeypatch.setattr(
		manager,
		'get_pipeline',
		lambda owner, pipeline_id: {
			'owner': owner,
			'pipeline_id': pipeline_id
		}
	)

	def find_existing(owner, pipeline_id, key, proposal):
		record = existing.get(key)

		if record is None:
			return None

		if record['fingerprint'] != idempotency.fingerprint(proposal):
			raise manager.PipelineError(
				'Idempotency key conflict', 409
			)

		return record['run']

	monkeypatch.setattr(
		bulk_registration,
		'_existing',
		find_existing
	)

	def check_proposal(owner, pipeline_id, proposal):
		if proposal['parameters']['target'] == 'BLOCKED':
			raise manager.PipelineError(
				'Target not plannable', 409
			)

	monkeypatch.setattr(
		bulk_registration,
		'_current_proposal',
		check_proposal
	)

	def create_run(owner, pipeline_id, payload, **kwargs):
		key = payload['idempotency_key']
		created.append(key)

		run = {
			'run_id': 'run-%d' % len(created),
			'node_id': payload['node_id'],
			'status': 'PLANNED',
			'idempotency_replayed': False
		}

		proposal = {
			k: v for k, v in payload.items()
			if k != 'idempotency_key'
		}

		existing[key] = {
			'fingerprint': idempotency.fingerprint(proposal),
			'run': run
		}

		return run

	monkeypatch.setattr(
		manager,
		'create_run_simple',
		create_run
	)

	return created, existing


def test_two_independent_registrations(monkeypatch):
	created, _ = setup_fakes(monkeypatch)

	result = bulk_registration.register(
		'alice',
		'p1',
		{
			'items': [
				item('key-a'),
				item('key-b', 'TARGET_B', 2)
			]
		}
	)

	assert result['summary'] == {
		'total': 2,
		'created': 2,
		'replayed': 0,
		'failed': 0
	}

	assert created == ['key-a', 'key-b']


def test_retry_returns_original_runs(monkeypatch):
	created, _ = setup_fakes(monkeypatch)

	payload = {'items': [item('key-a')]}

	first = bulk_registration.register('alice', 'p1', payload)
	second = bulk_registration.register('alice', 'p1', payload)

	assert first['items'][0]['status'] == 'CREATED'
	assert second['items'][0]['status'] == 'REPLAYED'
	assert first['items'][0]['run_id'] == second['items'][0]['run_id']
	assert created == ['key-a']


def test_key_reuse_with_different_request(monkeypatch):
	created, _ = setup_fakes(monkeypatch)

	bulk_registration.register(
		'alice', 'p1', {'items': [item('key-a')]}
	)

	result = bulk_registration.register(
		'alice',
		'p1',
		{'items': [item('key-a', 'TARGET_B', 2)]}
	)

	assert result['summary']['failed'] == 1
	assert result['items'][0]['http_status'] == 409
	assert created == ['key-a']


def test_partial_success(monkeypatch):
	created, _ = setup_fakes(monkeypatch)

	result = bulk_registration.register(
		'alice',
		'p1',
		{
			'items': [
				item('key-a'),
				item('key-b', 'BLOCKED', 2)
			]
		}
	)

	assert result['summary']['created'] == 1
	assert result['summary']['failed'] == 1
	assert created == ['key-a']


def test_duplicate_keys_rejected_before_registration(monkeypatch):
	created, _ = setup_fakes(monkeypatch)

	with pytest.raises(manager.PipelineError) as exc:
		bulk_registration.register(
			'alice',
			'p1',
			{
				'items': [
					item('same'),
					item('same', 'TARGET_B', 2)
				]
			}
		)

	assert exc.value.status == 400
	assert created == []


def test_duplicate_target_rejected(monkeypatch):
	created, _ = setup_fakes(monkeypatch)

	with pytest.raises(manager.PipelineError):
		bulk_registration.register(
			'alice',
			'p1',
			{
				'items': [
					item('key-a'),
					item('key-b')
				]
			}
		)

	assert created == []


def test_registration_requires_idempotency_key():
	with pytest.raises(manager.PipelineError) as exc:
		bulk_registration.validate_request({
			'items': [{
				'registration': registration()
			}]
		})

	assert exc.value.status == 400

