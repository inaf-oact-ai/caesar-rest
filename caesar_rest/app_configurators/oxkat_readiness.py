
"""Metadata-only scientific readiness for OXKAT targets.

No Measurement Set scans, filesystem checks, job submission or DB writes.
Candidate inputs are suggestions; V2 binding verifies them at registration.
"""

from caesar_rest import dataset_registry
from caesar_rest.pipeline import manager
from caesar_rest.pipeline import readiness as pipeline_readiness


def _reference(run, index):
	"""Return an explicit, path-free artifact reference."""
	artifact = run['artifacts'][index]

	return {
		'run_id': run['run_id'],
		'node_id': run['node_id'],
		'artifact': artifact['name'],
		'artifact_index': index
	}


def _selected_runs(pipeline, runs, snapshot, stage):
	"""Find selected and metadata-consumable runs for a given stage."""

	by_id = {
		run['run_id']: run
		for run in runs
		if isinstance(run, dict)
		and isinstance(run.get('run_id'), str)
	}

	result = []

	for node in snapshot['nodes']:
		if (
			node.get('stage') != stage
			or node.get('status') != 'READY'
			or not node.get('can_consume')
		):
			continue

		run_id = node.get('selected_run_id')
		run = by_id.get(run_id)

		if (
			run is not None
			and run.get('node_id') == node.get('node_id')
		):
			result.append(run)

	return result


def _target_ms_refs(run, artifact_name, target):
	"""Match the same target suffix used by OXKAT's V2 validator."""

	artifacts = run.get('artifacts') or []
	result = []

	for index, artifact in enumerate(artifacts):
		if not isinstance(artifact, dict):
			continue

		if (
			artifact.get('name') != artifact_name
			or artifact.get('kind') != 'directory'
		):
			continue

		path = artifact.get('relative_path')

		if not isinstance(path, str):
			continue

		filename = path.rsplit('/', 1)[-1]

		if filename.endswith('_' + target + '.ms'):
			result.append(_reference(run, index))

	return result


def _project_info_ref(run, by_id, pipeline_id):
	"""Resolve the frozen upstream project_info binding."""

	bindings = run.get('input_artifacts') or []
	matches = [
		binding for binding in bindings
		if isinstance(binding, dict)
		and binding.get('input_name') == 'project_info'
	]

	if len(matches) != 1:
		return None

	binding = matches[0]
	source_id = binding.get('source_run_id')
	index = binding.get('artifact_index')

	if (
		binding.get('source_pipeline_id') != pipeline_id
		or type(index) is not int
		or index < 0
	):
		return None

	source = by_id.get(source_id)

	if (
		source is None
		or source.get('node_id') != binding.get('source_node_id')
		or not manager.run_readiness(source)['readiness']['can_consume']
	):
		return None

	artifacts = source.get('artifacts')

	if not isinstance(artifacts, list) or index >= len(artifacts):
		return None

	artifact = artifacts[index]

	if (
		not isinstance(artifact, dict)
		or artifact.get('name') != 'project_info'
		or artifact.get('kind', 'file') != 'file'
		or binding.get('artifact_name') != 'project_info'
		or binding.get('artifact_kind') != 'file'
	):
		return None

	return _reference(source, index)


def _valid_flag_input(run, by_id, target):
	"""Verify the frozen FLAG input identifies the intended 1GC target."""

	bindings = run.get('input_artifacts') or []

	matches = [
		item for item in bindings
		if isinstance(item, dict)
		and item.get('input_name') == 'target_ms'
	]

	if len(matches) != 1:
		return False

	binding = matches[0]
	source = by_id.get(binding.get('source_run_id'))
	index = binding.get('artifact_index')

	if (
		source is None
		or type(index) is not int
		or index < 0
		or binding.get('source_pipeline_id') != run.get('pipeline_id')
		or binding.get('source_node_id') != source.get('node_id')
		or (source.get('parameters') or {}).get('stage') != '1GC'
	):
		return False

	artifacts = source.get('artifacts')

	if not isinstance(artifacts, list) or index >= len(artifacts):
		return False

	artifact = artifacts[index]
	path = artifact.get('relative_path')

	return (
		artifact.get('name') == 'working_measurement_sets'
		and artifact.get('kind') == 'directory'
		and isinstance(path, str)
		and path.rsplit('/', 1)[-1].endswith(
			'_' + target + '.ms'
		)
	)


def _flag_image_refs(run):
	"""Find retained FLAG image products required for 2GC."""

	return [
		_reference(run, index)
		for index, artifact in enumerate(run.get('artifacts') or [])
		if isinstance(artifact, dict)
		and artifact.get('name') == 'flag_images'
		and artifact.get('kind') == 'directory'
	]

def _result(candidates, missing_reason):
	"""Produce an unambiguous planning result."""

	if not candidates:
		return {
			'can_plan': False,
			'blocking_reasons': [missing_reason],
			'inputs': None
		}

	if len(candidates) != 1:
		return {
			'can_plan': False,
			'blocking_reasons': ['AMBIGUOUS_UPSTREAM_INPUTS'],
			'inputs': None
		}

	return {
		'can_plan': True,
		'blocking_reasons': [],
		'inputs': candidates[0]
	}


def resolve_snapshot(pipeline, runs, dataset_doc):
	"""Plan FLAG/2GC prerequisites from inspection and selected runs."""

	targets = dataset_registry.public_dataset_targets(dataset_doc)

	if targets['status'] != 'READY':
		return {
			'provider': 'oxkat',
			'status': 'INSPECTION_NOT_READY',
			'inspection_status': targets['status'],
			'targets': []
		}

	if (
		targets.get('fields_truncated') is not False
		or targets.get('rows_with_unreported_field') != 0
	):
		return {
			'provider': 'oxkat',
			'status': 'INSPECTION_INCOMPLETE',
			'inspection_status': 'READY',
			'targets': []
		}

	pipeline_id = pipeline['pipeline_id']
	snapshot = pipeline_readiness.resolve_snapshot(pipeline, runs)

	by_id = {
		run['run_id']: run
		for run in runs
		if isinstance(run, dict)
		and isinstance(run.get('run_id'), str)
	}

	gc1_runs = _selected_runs(pipeline, runs, snapshot, '1GC')
	flag_runs = _selected_runs(pipeline, runs, snapshot, 'FLAG')

	items = []

	for target in targets['science_targets']:
		name = target['name']

		flag_candidates = []

		for run in gc1_runs:
			project = _project_info_ref(run, by_id, pipeline_id)

			if project is None:
				continue

			for ms in _target_ms_refs(
				run, 'working_measurement_sets', name
			):
				flag_candidates.append({
					'target_ms': ms,
					'project_info': project
				})

		gc2_candidates = []

		for run in flag_runs:
			parameters = run.get('parameters') or {}

			if (
				not isinstance(parameters, dict)
				or parameters.get('target') != name
				or not _valid_flag_input(run, by_id, name)
			):
				continue

			project = _project_info_ref(run, by_id, pipeline_id)
			images = _flag_image_refs(run)

			if project is None or len(images) != 1:
				continue

			for ms in _target_ms_refs(
				run, 'flagged_target_measurement_sets', name
			):
				gc2_candidates.append({
					'target_ms': ms,
					'project_info': project,
					'flag_images': images[0]
				})		

		items.append({
			'field_id': target['field_id'],
			'name': name,
			'next_steps': {
				'FLAG': _result(
					flag_candidates,
					'NO_CONSUMABLE_1GC_TARGET_INPUTS'
				),
				'2GC': _result(
					gc2_candidates,
					'NO_CONSUMABLE_FLAG_TARGET_INPUTS'
				)
			}
		})

	return {
		'provider': 'oxkat',
		'status': 'READY',
		'inspection_status': 'READY',
		'target_count': len(items),
		'targets': items
	}

