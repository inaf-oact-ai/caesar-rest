
"""Generic, read-only Pipeline V2 readiness from persisted metadata.

No scientific stage policy, filesystem access, scheduler calls or writes.
This is a metadata snapshot, not a substitute for artifact binding checks.
"""

from caesar_rest.pipeline import manager


def _artifacts(run):
	"""Public artifact identities, without storage paths or checksums."""
	items = run.get('artifacts')
	if not isinstance(items, list):
		return []
	return [
		{
			'index': index,
			'name': item.get('name'),
			'kind': item.get('kind', 'file'),
			'role': item.get('role')
		}
		for index, item in enumerate(items)
		if isinstance(item, dict)
	]


def _dependencies(run, runs_by_id, pipeline_id):
	"""Check frozen reference consistency without opening artifacts.

	Do not require source runs to remain selected: bindings name exact runs.
	"""
	parents = run.get('input_runs')
	bindings = run.get('input_artifacts')
	problems = []
	dependencies = []

	if not isinstance(parents, list) or not isinstance(bindings, list):
		return [], ['INVALID_FROZEN_INPUTS']

	if any(not isinstance(value, str) or not value for value in parents):
		problems.append('INVALID_PARENT_RUN_ID')
	if len(parents) != len(set(str(value) for value in parents)):
		problems.append('DUPLICATE_PARENT_RUN')

	for parent_id in parents:
		parent = runs_by_id.get(parent_id) if isinstance(parent_id, str) else None
		if parent is None:
			problems.append('PARENT_RUN_MISSING')
		elif parent.get('status') != 'COMPLETED':
			problems.append('PARENT_RUN_NOT_COMPLETED')

	seen_names = set()
	for binding in bindings:
		if not isinstance(binding, dict):
			problems.append('INVALID_ARTIFACT_BINDING')
			continue

		name = binding.get('input_name')
		source_id = binding.get('source_run_id')
		index = binding.get('artifact_index')
		if not isinstance(name, str) or not name or name in seen_names:
			problems.append('INVALID_ARTIFACT_INPUT_NAME')
		else:
			seen_names.add(name)

		dependencies.append({
			'input_name': name,
			'source_run_id': source_id,
			'source_node_id': binding.get('source_node_id'),
			'artifact_index': index,
			'artifact_name': binding.get('artifact_name')
		})

		if (not isinstance(source_id, str) or source_id not in parents
				or binding.get('source_pipeline_id') != pipeline_id):
			problems.append('INVALID_ARTIFACT_SOURCE')
			continue

		parent = runs_by_id.get(source_id)
		if parent is None:
			problems.append('ARTIFACT_SOURCE_MISSING')
			continue

		if binding.get('source_node_id') != parent.get('node_id'):
			problems.append('ARTIFACT_SOURCE_NODE_MISMATCH')

		if not manager.run_readiness(parent)['readiness']['can_consume']:
			problems.append('ARTIFACT_SOURCE_NOT_CONSUMABLE')
			continue

		artifacts = parent.get('artifacts')
		retained = parent.get('retained_artifacts')
		if (type(index) is not int or index < 0
				or not isinstance(artifacts, list)
				or index >= len(artifacts)
				or not isinstance(retained, list)
				or index >= len(retained)):
			problems.append('ARTIFACT_INDEX_INVALID')
			continue

		artifact = artifacts[index]
		record = retained[index]
		if not isinstance(artifact, dict) or not isinstance(record, dict):
			problems.append('ARTIFACT_METADATA_INVALID')
			continue

		if (artifact.get('name') != binding.get('artifact_name')
				or artifact.get('kind', 'file') != binding.get('artifact_kind')
				or artifact.get('size_bytes') != binding.get('size_bytes')):
			problems.append('ARTIFACT_IDENTITY_MISMATCH')

		if record.get('index') != index:
			problems.append('ARTIFACT_RETENTION_MISMATCH')

		for key in ('sha256', 'manifest_sha256'):
			if key in binding and record.get(key) != binding[key]:
				problems.append('ARTIFACT_DIGEST_MISMATCH')

	return dependencies, sorted(set(problems))


def resolve_snapshot(pipeline, runs):
	"""Compute per-node readiness from a single metadata snapshot."""
	if not isinstance(pipeline, dict):
		raise manager.PipelineError('Invalid pipeline metadata', 409)

	selections = pipeline.get('selections') or {}
	node_stages = pipeline.get('node_stages') or {}
	if not isinstance(selections, dict) or not isinstance(node_stages, dict):
		raise manager.PipelineError('Invalid pipeline node metadata', 409)

	runs_by_node = {}
	runs_by_id = {}
	for run in runs:
		if not isinstance(run, dict):
			continue
		node_id = run.get('node_id')
		run_id = run.get('run_id')
		if not isinstance(node_id, str) or not isinstance(run_id, str):
			continue
		runs_by_node.setdefault(node_id, []).append(run)
		runs_by_id[run_id] = run

	nodes = []
	for node_id in sorted(set(runs_by_node) | set(node_stages) | set(selections)):
		node_runs = runs_by_node.get(node_id, [])
		observed_stages = {
			run['parameters']['stage']
			for run in node_runs
			if isinstance(run.get('parameters'), dict)
			and isinstance(run['parameters'].get('stage'), str)
		}
		declared_stage = node_stages.get(node_id)
		stage = declared_stage
		if stage is None and len(observed_stages) == 1:
			stage = next(iter(observed_stages))

		selection = selections.get(node_id)
		selected_id = selection.get('run_id') if isinstance(selection, dict) else None
		item = {
			'node_id': node_id,
			'stage': stage,
			'run_count': len(node_runs),
			'selected_run_id': selected_id,
			'status': 'NO_RUNS',
			'can_consume': False,
			'blocking_reasons': [],
			'run': None,
			'artifacts': [],
			'dependencies': []
		}

		if (len(observed_stages) > 1 or
				(declared_stage is not None and observed_stages
				and observed_stages != {declared_stage})):
			item['status'] = 'STAGE_MISMATCH'
			item['blocking_reasons'] = ['NODE_STAGE_INCONSISTENT']
		elif not node_runs:
			item['status'] = 'NO_RUNS'
			item['blocking_reasons'] = ['NO_REGISTERED_RUN']
		elif not isinstance(selected_id, str) or not selected_id:
			item['status'] = 'UNSELECTED'
			item['blocking_reasons'] = ['NO_SELECTED_RUN']
		else:
			matches = [run for run in node_runs if run.get('run_id') == selected_id]
			if len(matches) != 1:
				item['status'] = 'STALE_SELECTION'
				item['blocking_reasons'] = ['SELECTED_RUN_UNAVAILABLE']
			else:
				run = matches[0]
				readiness = manager.run_readiness(run)
				dependencies, problems = _dependencies(
					run, runs_by_id, pipeline.get('pipeline_id')
				)
				item['dependencies'] = dependencies
				item['run'] = {
					'run_id': run['run_id'],
					'status': run.get('status'),
					'artifacts_status': readiness['artifacts_status'],
					'dataset_id': run.get('dataset_id')
				}
				if (pipeline.get('dataset_id') is not None
						and run.get('dataset_id') is not None
						and run['dataset_id'] != pipeline['dataset_id']):
					problems.append('RUN_DATASET_MISMATCH')

				if run.get('status') != 'COMPLETED':
					item['status'] = 'NOT_COMPLETED'
					problems.append('SELECTED_RUN_NOT_COMPLETED')
				elif not readiness['readiness']['can_consume']:
					item['status'] = 'ARTIFACTS_NOT_READY'
					problems.append('SELECTED_ARTIFACTS_NOT_READY')
				elif problems:
					item['status'] = 'INVALID_DEPENDENCIES'
				else:
					item['status'] = 'READY'
					item['can_consume'] = True
					item['artifacts'] = _artifacts(run)
				item['blocking_reasons'] = sorted(set(problems))

		nodes.append(item)

	return {
		'schema': 'caesar.pipeline-readiness.v1',
		'pipeline_id': pipeline.get('pipeline_id'),
		'dataset_id': pipeline.get('dataset_id'),
		'application': pipeline.get('app'),
		'nodes': nodes
	}


def resolve(owner, pipeline_id):
	"""Read the owner-scoped pipeline and associated runs; never mutate DB."""
	pipeline = manager.get_pipeline(owner, pipeline_id)
	_, runs_collection, _ = manager.collections()
	runs = list(runs_collection.find({
		'owner': owner,
		'pipeline_id': pipeline_id
	}))
	return resolve_snapshot(pipeline, runs)

