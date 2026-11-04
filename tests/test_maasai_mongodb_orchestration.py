"""R4C.4B: MongoDB-backed MAASAI Pipeline V2 orchestration regression.

Run from the caesar-rest repository root:
    CAESAR_IDEMPOTENCY_TEST_URI='mongodb://localhost:27017' \
    CAESAR_IDEMPOTENCY_ALLOW_TEST_DB=YES \
    python -m pytest -q tests/test_maasai_mongodb_orchestration.py

Creates and drops a uniquely named test database. NEVER point the opt-in URI
at production credentials or use this test against a production MongoDB.

Exercises actual pipeline registration, MongoDB idempotency, readiness and
conditional selections. Only filesystem-backed artifact binding is replaced
by a metadata-only simulator. No Slurm, containers or scientific I/O.
"""

from copy import deepcopy
import os
import uuid
from types import SimpleNamespace

import pytest
from flask import Flask
from pymongo import MongoClient

from caesar_rest import dataset_registry
from caesar_rest.app_configurators import oxkat_readiness
from caesar_rest.pipeline import bulk_planning, bulk_registration, manager
from caesar_rest.pipeline.artifacts import binding as artifact_binding


OWNER = 'maasai-test-owner'
PIPELINE_ID = 'p-maasai-test'
DATASET_ID = 'd-maasai-test'
TARGETS = ((1, 'TARGET_A'), (2, 'TARGET_B'))


def artifact(name, path, kind='file'):
	return {
		'name': name,
		'relative_path': path,
		'kind': kind,
		'role': 'primary_result',
		'size_bytes': 100
	}


def retained(items):
	return [{'index': index, 'size_bytes': entry['size_bytes']}
		for index, entry in enumerate(items)]


def frozen(name, source, index):
	item = source['artifacts'][index]
	return {
		'input_name': name,
		'source_run_id': source['run_id'],
		'source_pipeline_id': PIPELINE_ID,
		'source_node_id': source['node_id'],
		'artifact_index': index,
		'artifact_name': item['name'],
		'artifact_kind': item['kind'],
		'size_bytes': item['size_bytes']
	}


def seed_run(run_id, node_id, stage, artifacts, bindings=(), target=None):
	return {
		'owner': OWNER,
		'pipeline_id': PIPELINE_ID,
		'run_id': run_id,
		'node_id': node_id,
		'run_name': 'seed-' + run_id,
		'sequence': 1,
		'application': 'oxkat',
		'operation': manager.default_node_id(stage),
		'status': 'COMPLETED',
		'parameters': {'stage': stage, 'target': target},
		'dataset_id': DATASET_ID if stage in ('GET_INFO', '1GC') else None,
		'input_artifacts': list(bindings),
		'input_runs': sorted({b['source_run_id'] for b in bindings}),
		'artifacts_registered_at': 'synthetic',
		'artifacts': artifacts,
		'retained_artifacts': retained(artifacts)
	}


def inspected_dataset():
	return {
		'dataset_id': DATASET_ID,
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
						{'field_id': field_id, 'field_name': target,
						 'classification': 'science_target'}
						for field_id, target in TARGETS
					]
				}
			}
		}
	}


@pytest.fixture
def persisted(monkeypatch):
	uri = os.environ.get('CAESAR_IDEMPOTENCY_TEST_URI')
	allowed = os.environ.get('CAESAR_IDEMPOTENCY_ALLOW_TEST_DB') == 'YES'
	if not uri or not allowed:
		pytest.skip('Dedicated MongoDB URI and explicit test opt-in required')

	client = MongoClient(uri, serverSelectionTimeoutMS=3000, retryWrites=False)
	client.admin.command('ping')
	database_name = 'caesar_maasai_integration_' + uuid.uuid4().hex
	db = client[database_name]
	flask_app = Flask(__name__)
	flask_app.config['PIPELINE_V2_APPLICATIONS'] = {
		'oxkat': {
			'parameters': {'stage': ['GET_INFO', '1GC', 'FLAG', '2GC']},
			'dataset_input_name': 'measurement_set',
			'input_options_by_stage': {
				'GET_INFO': {'input-ms': 'measurement_set'},
				'1GC': {'input-ms': 'measurement_set', 'project-info': 'project_info'},
				'FLAG': {'input-ms': 'target_ms', 'project-info': 'project_info'},
				'2GC': {
					'input-ms': 'target_ms',
					'project-info': 'project_info',
					'flag-images': 'flag_images'
				}
			}
		}
	}

	monkeypatch.setattr(manager, 'mongo', SimpleNamespace(db=db))
	monkeypatch.setattr(dataset_registry, 'get_dataset',
		lambda dataset_id: deepcopy(inspected_dataset()) if dataset_id == DATASET_ID
		else (_ for _ in ()).throw(dataset_registry.DatasetError('Not found', 404)))

	# These two boundaries are simulated: the real functions verify retained
	# filesystem content and resolve selected-node references. Here all input
	# references are explicit, and we check persisted identities/retention.
	def resolve_named(db_arg, owner, pipeline_id, inputs, pipeline=None):
		assert db_arg is db and owner == OWNER and pipeline_id == PIPELINE_ID
		assert pipeline and pipeline['dataset_id'] == DATASET_ID
		return [{
			'input_name': name,
			'source_run_id': reference['run_id'],
			'artifact_index': reference['artifact_index'],
			'expected_artifact_name': reference['artifact']
		} for name, reference in inputs.items()]

	def bind_inputs(db_arg, owner, pipeline_id, requests, retention_root, **kwargs):
		assert db_arg is db and pipeline_id == PIPELINE_ID and owner == OWNER
		result = []
		for request in requests:
			source = db.pipeline_runs.find_one({
				'owner': owner, 'pipeline_id': pipeline_id,
				'run_id': request['source_run_id']
			})
			if source is None or not manager.run_readiness(source)['readiness']['can_consume']:
				raise manager.PipelineError('Upstream is not consumable', 409)
			index = request['artifact_index']
			if type(index) is not int or index < 0 or index >= len(source['artifacts']):
				raise manager.PipelineError('Artifact index invalid', 409)
			if source['artifacts'][index]['name'] != request['expected_artifact_name']:
				raise manager.PipelineError('Artifact name mismatch', 409)
			result.append(frozen(request['input_name'], source, index))
		return result

	monkeypatch.setattr(artifact_binding, 'resolve_named_inputs', resolve_named)
	monkeypatch.setattr(artifact_binding, 'bind_inputs', bind_inputs)

	with flask_app.app_context():
		manager.ensure_indexes()
		pipeline = {
			'owner': OWNER, 'pipeline_id': PIPELINE_ID, 'app': 'oxkat',
			'dataset_id': DATASET_ID,
			'node_stages': {'info': 'GET_INFO', 'calibration': '1GC'},
			'selections': {
				'info': {'run_id': 'info1'},
				'calibration': {'run_id': 'gc1'}
			}
		}
		db.pipelines.insert_one(pipeline)
		info = seed_run('info1', 'info', 'GET_INFO', [
			artifact('project_info', 'results/project_info.json')
		])
		gc1 = seed_run('gc1', 'calibration', '1GC', [
			artifact('working_measurement_sets',
				'results/calibrated_%s.ms' % target, 'directory')
			for _, target in TARGETS
		], [frozen('project_info', info, 0)])
		db.pipeline_runs.insert_many([info, gc1])

		try:
			yield db
		finally:
			client.drop_database(database_name)
			client.close()


def plan(stage, targets=None):
	payload = {'stage': stage}
	if targets is not None:
		payload['targets'] = targets
	return bulk_planning.plan(OWNER, PIPELINE_ID, payload)


def bulk(plan_result, prefix):
	return bulk_registration.register(OWNER, PIPELINE_ID, {
		'items': [{
			'idempotency_key': '%s:%s' % (prefix, item['target']),
			'registration': deepcopy(item['registration'])
		} for item in plan_result['items'] if item['can_register']]
	})


def complete_flag(db, run_id, target, *, retained_ok=True):
	items = [
		artifact('flagged_target_measurement_sets',
			'results/flagged_%s.ms' % target, 'directory'),
		artifact('flag_images', 'results/IMAGES', 'directory')
	]
	update = {
		'status': 'COMPLETED',
		'artifacts': items,
		'artifacts_registered_at': 'synthetic',
		'retained_artifacts': retained(items) if retained_ok else [],
		'retention_status': 'READY' if retained_ok else 'PENDING'
	}
	assert db.pipeline_runs.update_one({'run_id': run_id}, {'$set': update}).matched_count == 1


def test_actual_bulk_registration_persists_two_frozen_runs(persisted):
	response = plan('FLAG')
	assert response['summary'] == {'total': 2, 'plannable': 2, 'blocked': 0}
	result = bulk(response, 'flag:first')
	assert result['summary'] == {'total': 2, 'created': 2, 'replayed': 0, 'failed': 0}
	for entry in result['items']:
		run = persisted.pipeline_runs.find_one({'run_id': entry['run_id']})
		assert run['status'] == 'PLANNED' and run['job_id'] is None
		assert run['dataset_id'] is None
		assert len(run['input_artifacts']) == 2
		assert set(run['input_runs']) == {'gc1', 'info1'}
		assert all(b['source_pipeline_id'] == PIPELINE_ID for b in run['input_artifacts'])
	assert persisted.pipeline_runs.count_documents({'status': 'PLANNED'}) == 2


def test_actual_replay_survives_changed_selection_and_freezes_inputs(persisted):
	proposal = plan('FLAG', ['TARGET_A'])
	first = bulk(proposal, 'flag:replay')['items'][0]
	run_before = persisted.pipeline_runs.find_one({'run_id': first['run_id']})
	frozen_before = deepcopy(run_before['input_artifacts'])
	# Remove preferred 1GC selection. New planning is now blocked.
	persisted.pipelines.update_one({'pipeline_id': PIPELINE_ID},
		{'$unset': {'selections.calibration': ''}})
	assert plan('FLAG')['summary']['plannable'] == 0
	replay = bulk(proposal, 'flag:replay')['items'][0]
	assert replay['status'] == 'REPLAYED' and replay['run_id'] == first['run_id']
	assert persisted.pipeline_runs.count_documents({'idempotency_key': 'flag:replay:TARGET_A'}) == 1
	assert persisted.pipeline_runs.find_one({'run_id': first['run_id']})['input_artifacts'] == frozen_before


def test_actual_cas_selection_staleness_and_independent_2gc(persisted):
	registered = bulk(plan('FLAG'), 'flag:for2gc')['items']
	by_target = {entry['node_id']: entry['run_id'] for entry in registered}
	a = by_target['stage_flag_f1']
	b = by_target['stage_flag_f2']
	complete_flag(persisted, a, 'TARGET_A')
	complete_flag(persisted, b, 'TARGET_B', retained_ok=False)

	# Noncompleted and missing runs cannot be preferred. An accepted selection
	# is compare-and-set against the actual MongoDB document.
	selected_a = manager.select_run_conditional(OWNER, PIPELINE_ID,
		'stage_flag_f1', a, None)
	assert selected_a['run_id'] == a
	manager.select_run_conditional(OWNER, PIPELINE_ID, 'stage_flag_f2', b, None)
	with pytest.raises(manager.PipelineError) as error:
		manager.select_run_conditional(OWNER, PIPELINE_ID,
			'stage_flag_f1', a, None)
	assert error.value.status == 409

	ready = plan('2GC')
	assert ready['summary'] == {'total': 2, 'plannable': 1, 'blocked': 1}
	assert ready['items'][0]['registration']['inputs']['target_ms']['run_id'] == a
	assert ready['items'][1]['registration'] is None
	assert 'NO_CONSUMABLE_FLAG_TARGET_INPUTS' in ready['items'][1]['blocking_reasons']
	second = bulk(ready, '2gc:first')
	assert second['summary']['created'] == 1
	gc2 = persisted.pipeline_runs.find_one({'run_id': second['items'][0]['run_id']})
	assert gc2['node_id'] == 'stage_2gc_f1'
	assert len(gc2['input_artifacts']) == 3
	assert set(gc2['input_runs']) == {a, 'info1'}


def test_actual_idempotency_conflict_is_item_failure(persisted):
	proposal = plan('FLAG', ['TARGET_A'])
	first = bulk(proposal, 'flag:conflict')
	assert first['summary']['created'] == 1
	modified = deepcopy(proposal['items'][0]['registration'])
	modified['inputs']['target_ms']['artifact_index'] = 99
	result = bulk_registration.register(OWNER, PIPELINE_ID, {'items': [{
		'idempotency_key': 'flag:conflict:TARGET_A',
		'registration': modified
	}]})
	assert result['items'][0]['status'] == 'FAILED'
	assert result['items'][0]['http_status'] == 409
	assert persisted.pipeline_runs.count_documents({'idempotency_key': 'flag:conflict:TARGET_A'}) == 1
