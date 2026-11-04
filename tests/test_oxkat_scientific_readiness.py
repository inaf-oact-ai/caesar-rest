
"""Scientific readiness tests without executing OXKAT."""

from caesar_rest.app_configurators import oxkat_readiness
from caesar_rest.pipeline import scientific_readiness

def target_binding():
	return {
		'input_name': 'target_ms',
		'source_run_id': 'gc1',
		'source_pipeline_id': 'p1',
		'source_node_id': 'calibration',
		'artifact_index': 0,
		'artifact_name': 'working_measurement_sets',
		'artifact_kind': 'directory',
		'size_bytes': 100
	}
	
def dataset():
	return {
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
						{
							'field_id': 1,
							'field_name': 'TARGET_A',
							'classification': 'science_target'
						}
					]
				}
			}
		}
	}


def pipeline():
	return {
		'pipeline_id': 'p1',
		'app': 'oxkat',
		'dataset_id': 'dataset1',
		'node_stages': {
			'info': 'GET_INFO',
			'calibration': '1GC',
			'flagging': 'FLAG'
		},
		'selections': {
			'info': {'run_id': 'info1'},
			'calibration': {'run_id': 'gc1'}
		}
	}


def artifact(name, path, kind='file'):
	return {
		'name': name,
		'kind': kind,
		'relative_path': path,
		'size_bytes': 100,
		'role': 'primary_result'
	}


def run(run_id, node, stage, artifacts, bindings=None, target=None):
	return {
		'run_id': run_id,
		'pipeline_id': 'p1',
		'node_id': node,
		'status': 'COMPLETED',
		'parameters': {'stage': stage, 'target': target},
		'input_runs': sorted({
			item['source_run_id']
			for item in (bindings or [])
		}),
		'input_artifacts': bindings or [],
		'artifacts_registered_at': 'now',
		'artifacts': artifacts,
		'retained_artifacts': [
			{'index': index, 'size_bytes': 100}
			for index in range(len(artifacts))
		]
	}


def binding(source, node):
	return {
		'input_name': 'project_info',
		'source_run_id': source,
		'source_pipeline_id': 'p1',
		'source_node_id': node,
		'artifact_index': 0,
		'artifact_name': 'project_info',
		'artifact_kind': 'file',
		'size_bytes': 100
	}


def runs():
	return [
		run(
			'info1',
			'info',
			'GET_INFO',
			[artifact('project_info', 'results/project_info.json')]
		),
		run(
			'gc1',
			'calibration',
			'1GC',
			[
				artifact(
					'working_measurement_sets',
					'results/calibrated_TARGET_A.ms',
					'directory'
				)
			],
			bindings=[binding('info1', 'info')]
		)
	]


def target(result):
	return result['targets'][0]


def test_flag_ready_from_selected_1gc():
	result = oxkat_readiness.resolve_snapshot(
		pipeline(), runs(), dataset()
	)

	flag = target(result)['next_steps']['FLAG']
	gc2 = target(result)['next_steps']['2GC']

	assert flag['can_plan'] is True
	assert flag['inputs']['target_ms']['run_id'] == 'gc1'
	assert flag['inputs']['target_ms']['artifact_index'] == 0
	assert flag['inputs']['project_info']['run_id'] == 'info1'
	assert gc2['can_plan'] is False


def test_unselected_1gc_is_not_usable():
	p = pipeline()
	del p['selections']['calibration']

	result = oxkat_readiness.resolve_snapshot(
		p, runs(), dataset()
	)

	assert target(result)['next_steps']['FLAG']['can_plan'] is False


def test_2gc_ready_from_selected_flag():
	p = pipeline()
	p['selections']['flagging'] = {'run_id': 'flag1'}

	items = runs() + [
		run(
			'flag1',
			'flagging',
			'FLAG',
			[
				artifact(
					'flagged_target_measurement_sets',
					'results/flagged_TARGET_A.ms',
					'directory'
				),
				artifact(
					'flag_images',
					'results/IMAGES',
					'directory'
				)
			],
			bindings=[
				binding('info1', 'info'),
				target_binding()
			],
			target='TARGET_A'
		)
	]

	result = oxkat_readiness.resolve_snapshot(
		p, items, dataset()
	)

	gc2 = target(result)['next_steps']['2GC']

	assert gc2['can_plan'] is True
	assert gc2['inputs']['target_ms']['run_id'] == 'flag1'
	assert gc2['inputs']['flag_images']['artifact_index'] == 1
	assert gc2['inputs']['project_info']['run_id'] == 'info1'

def test_inspection_not_ready():
	d = dataset()
	d['inspection']['status'] = 'PENDING'

	result = oxkat_readiness.resolve_snapshot(
		pipeline(), runs(), d
	)

	assert result['status'] == 'INSPECTION_NOT_READY'
	assert result['targets'] == []


def test_generic_dispatcher_uses_provider_interface():
	class FakeProvider:
		def build_scientific_readiness(self, pipeline, runs, dataset_doc):
			return {'provider': 'fake', 'status': 'READY'}

	result = scientific_readiness.resolve_snapshot(
		{
			'pipeline_id': 'p1',
			'app': 'other_application',
			'dataset_id': 'dataset1'
		},
		[],
		{'dataset_id': 'dataset1'},
		FakeProvider()
	)

	assert result['application'] == 'other_application'
	assert result['scientific']['provider'] == 'fake'

