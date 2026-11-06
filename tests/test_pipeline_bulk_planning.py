
"""Read-only bulk planning tests without Slurm or MongoDB."""

import pytest

from caesar_rest.pipeline import bulk_planning
from caesar_rest.pipeline import manager
from caesar_rest.app_configurators import oxkat_readiness


def scientific_snapshot():
	return {
		'pipeline_id': 'p1',
		'dataset_id': 'dataset1',
		'application': 'oxkat',
		'scientific': {
			'provider': 'oxkat',
			'status': 'READY',
			'targets': [
				{
					'field_id': 1,
					'name': 'TARGET_A',
					'next_steps': {
						'FLAG': {
							'can_plan': True,
							'blocking_reasons': [],
							'inputs': {
								'target_ms': {
									'run_id': 'gc1',
									'node_id': 'stage_1gc',
									'artifact': 'working_measurement_sets',
									'artifact_index': 3
								},
								'project_info': {
									'run_id': 'info1',
									'node_id': 'stage_get_info',
									'artifact': 'project_info',
									'artifact_index': 8
								}
							}
						},
						'2GC': {
							'can_plan': False,
							'blocking_reasons': [
								'NO_CONSUMABLE_FLAG_TARGET_INPUTS'
							],
							'inputs': None
						}
					}
				},
				{
					'field_id': 2,
					'name': 'TARGET_B',
					'next_steps': {
						'FLAG': {
							'can_plan': False,
							'blocking_reasons': [
								'NO_CONSUMABLE_1GC_TARGET_INPUTS'
							],
							'inputs': None
						},
						'2GC': {
							'can_plan': False,
							'blocking_reasons': [
								'NO_CONSUMABLE_FLAG_TARGET_INPUTS'
							],
							'inputs': None
						}
					}
				}
			]
		}
	}


class OxkatProvider:
	def build_bulk_plan(self, scientific, stage, targets=None):
		return oxkat_readiness.build_bulk_plan(
			scientific, stage, targets
		)


def test_ready_and_blocked_targets():
	result = bulk_planning.plan_snapshot(
		scientific_snapshot(),
		'FLAG',
		None,
		OxkatProvider()
	)

	assert result['summary'] == {
		'total': 2,
		'plannable': 1,
		'blocked': 1
	}

	ready, blocked = result['items']

	assert ready['can_register'] is True
	assert ready['registration'] == {
		'stage': 'FLAG',
		'node_id': 'stage_flag_f1',
		'parameters': {
			'target': 'TARGET_A'
		},
		'inputs': {
			'target_ms': {
				'run_id': 'gc1',
				'artifact': 'working_measurement_sets',
				'artifact_index': 3
			},
			'project_info': {
				'run_id': 'info1',
				'artifact': 'project_info',
				'artifact_index': 8
			}
		}
	}

	assert blocked['can_register'] is False
	assert blocked['registration'] is None


def test_target_subset():
	result = bulk_planning.plan_snapshot(
		scientific_snapshot(),
		'FLAG',
		['TARGET_B'],
		OxkatProvider()
	)

	assert result['summary']['total'] == 1
	assert result['items'][0]['target'] == 'TARGET_B'


def test_unknown_target_rejected():
	with pytest.raises(manager.PipelineError) as exc:
		bulk_planning.plan_snapshot(
			scientific_snapshot(),
			'FLAG',
			['UNKNOWN'],
			OxkatProvider()
		)

	assert exc.value.status == 400


def test_no_2gc_inputs():
	result = bulk_planning.plan_snapshot(
		scientific_snapshot(),
		'2GC',
		None,
		OxkatProvider()
	)

	assert result['summary']['plannable'] == 0
	assert result['summary']['blocked'] == 2


def test_generic_dispatch_to_unrelated_application():
	class OtherProvider:
		def build_bulk_plan(self, scientific, stage, targets=None):
			return {
				'status': 'READY',
				'items': [{
					'can_register': False,
					'registration': None,
					'blocking_reasons': ['NOT_READY']
				}]
			}

	result = bulk_planning.plan_snapshot(
		{
			'pipeline_id': 'p2',
			'dataset_id': 'd2',
			'application': 'other_app',
			'scientific': {'status': 'READY'}
		},
		'TRAIN',
		None,
		OtherProvider()
	)

	assert result['application'] == 'other_app'
	assert result['stage'] == 'TRAIN'
	assert result['summary']['blocked'] == 1


def test_invalid_request():
	with pytest.raises(manager.PipelineError):
		bulk_planning.validate_request({
			'stage': 'FLAG',
			'targets': ['TARGET_A', 'TARGET_A']
		})

	with pytest.raises(manager.PipelineError):
		bulk_planning.validate_request({
			'stage': 'FLAG',
			'dataset_id': 'other_dataset'
		})

