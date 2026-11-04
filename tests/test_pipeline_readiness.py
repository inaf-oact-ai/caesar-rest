
"""Metadata-only tests for generic Pipeline V2 readiness."""

from caesar_rest.pipeline import readiness


def pipeline():
	return {
		'pipeline_id': 'p1',
		'app': 'arbitrary_app',
		'dataset_id': 'dataset1',
		'node_stages': {
			'source': 'CALIBRATE',
			'sink': 'PROCESS',
			'empty': 'EXPORT'
		},
		'selections': {
			'source': {'run_id': 'r1'},
			'sink': {'run_id': 'r2'}
		}
	}


def completed(run_id, node, stage, retained=True, inputs=None, parents=None):
	return {
		'run_id': run_id,
		'node_id': node,
		'status': 'COMPLETED',
		'parameters': {'stage': stage},
		'dataset_id': 'dataset1' if node == 'source' else None,
		'input_runs': [] if parents is None else parents,
		'input_artifacts': [] if inputs is None else inputs,
		'artifacts_registered_at': 'now',
		'artifacts': [
			{
				'name': 'result',
				'kind': 'file',
				'role': 'primary_result',
				'size_bytes': 5
			}
		],
		'retained_artifacts': (
			[{'index': 0, 'sha256': 'a' * 64, 'size_bytes': 5}]
			if retained else None
		),
		'retention_status': 'READY' if retained else 'PENDING'
	}


def frozen_input():
	return {
		'input_name': 'data',
		'source_run_id': 'r1',
		'source_pipeline_id': 'p1',
		'source_node_id': 'source',
		'artifact_index': 0,
		'artifact_name': 'result',
		'artifact_kind': 'file',
		'size_bytes': 5,
		'sha256': 'a' * 64
	}


def node(result, name):
	return next(
		item for item in result['nodes']
		if item['node_id'] == name
	)


def test_ready_and_empty_nodes():
	result = readiness.resolve_snapshot(
		pipeline(),
		[
			completed('r1', 'source', 'CALIBRATE'),
			completed(
				'r2',
				'sink',
				'PROCESS',
				inputs=[frozen_input()],
				parents=['r1']
			)
		]
	)

	assert node(result, 'source')['status'] == 'READY'
	assert node(result, 'sink')['status'] == 'READY'
	assert node(result, 'empty')['status'] == 'NO_RUNS'
	assert node(result, 'sink')['dependencies'][0]['source_run_id'] == 'r1'
	assert 'relative_path' not in str(result)


def test_unselected_and_stale_selection():
	p = pipeline()
	p['selections'] = {
		'source': {'run_id': 'missing'}
	}

	result = readiness.resolve_snapshot(
		p,
		[
			completed('r1', 'source', 'CALIBRATE')
		]
	)

	assert node(result, 'source')['status'] == 'STALE_SELECTION'
	assert node(result, 'source')['can_consume'] is False


def test_incomplete_retention_blocks_consumption():
	result = readiness.resolve_snapshot(
		pipeline(),
		[
			completed(
				'r1',
				'source',
				'CALIBRATE',
				retained=False
			)
		]
	)

	assert node(result, 'source')['status'] == 'ARTIFACTS_NOT_READY'


def test_frozen_dependency_mismatch():
	bad = frozen_input()
	bad['sha256'] = 'b' * 64

	result = readiness.resolve_snapshot(
		pipeline(),
		[
			completed('r1', 'source', 'CALIBRATE'),
			completed(
				'r2',
				'sink',
				'PROCESS',
				inputs=[bad],
				parents=['r1']
			)
		]
	)

	assert node(result, 'sink')['status'] == 'INVALID_DEPENDENCIES'
	assert 'ARTIFACT_DIGEST_MISMATCH' in (
		node(result, 'sink')['blocking_reasons']
	)


def test_stage_mismatch_and_independent_selections():
	p = pipeline()
	p['selections'] = {
		'source': {'run_id': 'r1'}
	}

	result = readiness.resolve_snapshot(
		p,
		[
			completed('r1', 'source', 'DIFFERENT_STAGE'),
			completed('r2', 'sink', 'PROCESS')
		]
	)

	assert node(result, 'source')['status'] == 'STAGE_MISMATCH'
	assert node(result, 'sink')['status'] == 'UNSELECTED'

