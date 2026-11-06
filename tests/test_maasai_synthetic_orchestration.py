"""R4C.4B synthetic MAASAI multi-target orchestration regression.

Run from the caesar-rest repository root:
    python -m pytest -q tests/test_maasai_synthetic_orchestration.py

Exercises real OXKAT scientific readiness, planning and controlled bulk
registration logic with synthetic metadata. No MongoDB, Slurm or containers.
"""

from copy import deepcopy

import pytest

from caesar_rest.app_configurators import oxkat_readiness
from caesar_rest.pipeline import bulk_planning, bulk_registration, idempotency, manager


TARGETS = ((1, 'TARGET_A'), (2, 'TARGET_B'))


def artifact(name, path, kind='file'):
	return {
		'name': name, 'relative_path': path, 'kind': kind,
		'size_bytes': 100, 'role': 'primary_result'
	}


def binding(name, source, index):
	item = source['artifacts'][index]
	return {
		'input_name': name,
		'source_run_id': source['run_id'],
		'source_pipeline_id': source['pipeline_id'],
		'source_node_id': source['node_id'],
		'artifact_index': index,
		'artifact_name': item['name'],
		'artifact_kind': item['kind'],
		'size_bytes': item['size_bytes']
	}


def completed(run_id, node_id, stage, artifacts, bindings=(), target=None):
	return {
		'run_id': run_id,
		'pipeline_id': 'pipeline1',
		'node_id': node_id,
		'status': 'COMPLETED',
		'parameters': {'stage': stage, 'target': target},
		'input_artifacts': list(bindings),
		'input_runs': sorted(set(b['source_run_id'] for b in bindings)),
		'artifacts_registered_at': 'synthetic',
		'artifacts': artifacts,
		'retained_artifacts': [
			{'index': i, 'size_bytes': 100}
			for i in range(len(artifacts))
		]
	}


class Harness:
	def __init__(self):
		self.dataset = {
			'dataset_id': 'dataset1',
			'inspection': {
				'status': 'READY',
				'schema': 'caesar.dataset-inspection.msv2.v1',
				'detected_format': 'casa-measurement-set-v2',
				'metadata': {
					'field_observations': {
						'available': True,
						'fields_truncated': False,
						'rows_with_unreported_field': 0,
						'fields': [
							{'field_id': i, 'field_name': name,
							 'classification': 'science_target'}
							for i, name in TARGETS
						]
					}
				}
			}
		}
		self.pipeline = {
			'pipeline_id': 'pipeline1',
			'dataset_id': 'dataset1',
			'app': 'oxkat',
			'node_stages': {'info': 'GET_INFO', 'calibration': '1GC'},
			'selections': {
				'info': {'run_id': 'info1'},
				'calibration': {'run_id': 'gc1'}
			}
		}
		info = completed('info1', 'info', 'GET_INFO', [
			artifact('project_info', 'results/project_info.json')
		])
		gc1 = completed('gc1', 'calibration', '1GC', [
			artifact('working_measurement_sets',
				'results/calibrated_%s.ms' % target, 'directory')
			for _, target in TARGETS
		], [binding('project_info', info, 0)])
		self.runs = [info, gc1]
		self.by_key = {}
		self.created = 0
		self.reject_targets = set()

	def scientific(self):
		return oxkat_readiness.resolve_snapshot(
			self.pipeline, self.runs, self.dataset
		)

	def plan(self, stage, targets=None):
		class Provider:
			def build_bulk_plan(self, scientific, stage, targets=None):
				return oxkat_readiness.build_bulk_plan(
					scientific, stage, targets
				)
		return bulk_planning.plan_snapshot(
			{
				'pipeline_id': 'pipeline1', 'dataset_id': 'dataset1',
				'application': 'oxkat', 'scientific': self.scientific()
			}, stage, targets, Provider()
		)

	def attach(self, monkeypatch):
		monkeypatch.setattr(
			manager, 'get_pipeline',
			lambda owner, pipeline_id: self.pipeline
		)

		def existing(owner, pipeline_id, key, proposal):
			item = self.by_key.get((owner, pipeline_id, key))
			if item is None:
				return None
			if item['fingerprint'] != idempotency.fingerprint(proposal):
				raise manager.PipelineError('Idempotency key conflict', 409)
			return item['run']

		def current(owner, pipeline_id, proposal):
			target = proposal['parameters']['target']
			if target in self.reject_targets:
				raise manager.PipelineError('Synthetic target rejected', 409)
			items = self.plan(proposal['stage'], [target])['items']
			if len(items) != 1 or not items[0]['can_register']:
				raise manager.PipelineError('Not plannable', 409)
			if items[0]['registration'] != proposal:
				raise manager.PipelineError('Stale proposal', 409)

		def create(owner, pipeline_id, payload, **kwargs):
			self.created += 1
			proposal = {k: v for k, v in payload.items()
				if k != 'idempotency_key'}
			run = {
				'run_id': 'registered%d' % self.created,
				'node_id': payload['node_id'],
				'status': 'PLANNED',
				'idempotency_replayed': False
			}
			self.by_key[(owner, pipeline_id, payload['idempotency_key'])] = {
				'fingerprint': idempotency.fingerprint(proposal),
				'run': run
			}
			return run

		monkeypatch.setattr(bulk_registration, '_existing', existing)
		monkeypatch.setattr(bulk_registration, '_current_proposal', current)
		monkeypatch.setattr(manager, 'create_run_simple', create)

	def bulk(self, plan, prefix='key'):
		return bulk_registration.register('alice', 'pipeline1', {
			'items': [
				{'idempotency_key': '%s-%s' % (prefix, item['target']),
				 'registration': deepcopy(item['registration'])}
				for item in plan['items'] if item['can_register']
			]
		})

	def add_flag(self, target, node_id, run_id, retained=True):
		info, gc1 = self.runs[:2]
		idx = [name for _, name in TARGETS].index(target)
		run = completed(run_id, node_id, 'FLAG', [
			artifact('flagged_target_measurement_sets',
				'results/flagged_%s.ms' % target, 'directory'),
			artifact('flag_images', 'results/IMAGES', 'directory')
		], [binding('target_ms', gc1, idx),
			binding('project_info', info, 0)], target)
		if not retained:
			run['retained_artifacts'] = []
		self.runs.append(run)
		self.pipeline['node_stages'][node_id] = 'FLAG'
		self.pipeline['selections'][node_id] = {'run_id': run_id}
		return run


@pytest.fixture
def harness(monkeypatch):
	h = Harness()
	h.attach(monkeypatch)
	return h


def test_independent_flag_planning_and_registration(harness):
	plan = harness.plan('FLAG')
	assert plan['schema'] == 'caesar.pipeline-bulk-plan.v1'
	assert plan['summary'] == {'total': 2, 'plannable': 2, 'blocked': 0}
	assert [i['registration']['node_id'] for i in plan['items']] == [
		'stage_flag_f1', 'stage_flag_f2'
	]
	for item in plan['items']:
		assert 'dataset_id' not in item['registration']
		assert item['registration']['inputs']['target_ms']['run_id'] == 'gc1'
	result = harness.bulk(plan)
	assert result['summary'] == {'total': 2, 'created': 2,
		'replayed': 0, 'failed': 0}
	assert harness.created == 2


def test_registration_replay_after_upstream_selection_change(harness):
	plan = harness.plan('FLAG')
	first = harness.bulk(plan)
	original = [x['run_id'] for x in first['items']]
	harness.pipeline['selections']['calibration'] = {'run_id': 'other-gc1'}
	assert harness.plan('FLAG')['summary']['plannable'] == 0
	replayed = harness.bulk(plan)
	assert [x['status'] for x in replayed['items']] == ['REPLAYED', 'REPLAYED']
	assert [x['run_id'] for x in replayed['items']] == original
	assert harness.created == 2


def test_stale_proposal_and_partial_failure(harness):
	plan = harness.plan('FLAG')
	harness.reject_targets.add('TARGET_B')
	result = harness.bulk(plan)
	assert result['summary']['created'] == 1
	assert result['summary']['failed'] == 1
	assert result['items'][1]['http_status'] == 409
	assert harness.created == 1
	# The previously successful target can safely be replayed.
	replay = harness.bulk(harness.plan('FLAG', ['TARGET_A']))
	assert replay['items'][0]['status'] == 'REPLAYED'


def test_2gc_can_progress_per_target_without_other_retention(harness):
	harness.add_flag('TARGET_A', 'stage_flag_f1', 'flag-a')
	harness.add_flag('TARGET_B', 'stage_flag_f2', 'flag-b', retained=False)
	plan = harness.plan('2GC')
	assert plan['summary'] == {'total': 2, 'plannable': 1, 'blocked': 1}
	a, b = plan['items']
	assert a['registration']['node_id'] == 'stage_2gc_f1'
	assert a['registration']['inputs']['target_ms']['run_id'] == 'flag-a'
	assert a['registration']['inputs']['flag_images']['run_id'] == 'flag-a'
	assert b['registration'] is None
	assert 'NO_CONSUMABLE_FLAG_TARGET_INPUTS' in b['blocking_reasons']
	registered = harness.bulk(plan, prefix='2gc')
	assert registered['summary']['created'] == 1


def test_inspection_not_ready_blocks_planning(harness):
	harness.dataset['inspection']['status'] = 'PENDING'
	plan = harness.plan('FLAG')
	assert plan['status'] == 'BLOCKED'
	assert plan['items'] == []
	assert plan['summary']['total'] == 0


def test_idempotency_key_cannot_be_reused_for_different_inputs(harness):
	plan = harness.plan('FLAG', ['TARGET_A'])
	first = harness.bulk(plan)
	assert first['items'][0]['status'] == 'CREATED'
	modified = deepcopy(plan['items'][0]['registration'])
	modified['inputs']['target_ms']['artifact_index'] = 99
	failed = bulk_registration.register('alice', 'pipeline1', {
		'items': [{
			'idempotency_key': 'key-TARGET_A',
			'registration': modified
		}]
	})
	assert failed['items'][0]['status'] == 'FAILED'
	assert failed['items'][0]['http_status'] == 409
	assert harness.created == 1
