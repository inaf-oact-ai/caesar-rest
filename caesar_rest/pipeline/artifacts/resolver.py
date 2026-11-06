
"""Owner-scoped resolution of registered Pipeline V2 artifact files.

Selected is a late-bound alias; callers comparing runs should use explicit run IDs.
Only the trusted artifact registry supplies paths to the underlying safe file opener.
"""

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import access


def get_artifact_run(db, owner, pipeline_id, node_id, run_ref):
	"""Return a run by explicit ID or the current node selection."""
	manager.validate_identifier(node_id, 'node_id')
	if run_ref == 'selected':
		# Use the passed database (also works in standalone code and unit tests).
		pipeline = db.pipelines.find_one({
			'pipeline_id': pipeline_id,
			'owner': owner
		})
		if pipeline is None:
			raise manager.PipelineError('Pipeline not found', 404)
		selection = (pipeline.get('selections') or {}).get(node_id) or {}
		run_id = selection.get('run_id')
		if not isinstance(run_id, str) or not run_id:
			raise manager.PipelineError('No run selected for node', 409)
	else:
		run_id = run_ref
	return access.get_run(db, owner, pipeline_id, node_id, run_id)


def find_artifact_index(run, artifact_name=None, relative_path=None):
	"""Find exactly one registered artifact by name and/or exact relative path."""
	if (artifact_name is None) == (relative_path is None):
		raise manager.PipelineError('Supply exactly one artifact selector', 400)
	if run.get('status') != 'COMPLETED':
		raise manager.PipelineError('Run is not completed', 409)
	if not run.get('artifacts_registered_at'):
		raise manager.PipelineError('Run artifacts are not registered', 409)

	if artifact_name is not None:
		if not isinstance(artifact_name, str) or not artifact_name or '/' in artifact_name or '\\' in artifact_name or '\x00' in artifact_name:
			raise manager.PipelineError('Invalid artifact name', 400)
		matches = [index for index, artifact in enumerate(run.get('artifacts') or [])
			if artifact.get('name') == artifact_name]
	else:
		try:
			access._safe_parts(relative_path)
		except access.ArtifactAccessError as exc:
			raise manager.PipelineError('Invalid artifact relative path', 400) from exc
		matches = [index for index, artifact in enumerate(run.get('artifacts') or [])
			if artifact.get('relative_path') == relative_path]

	if not matches:
		raise manager.PipelineError('Artifact not found in run', 404)
	if len(matches) > 1:
		raise manager.PipelineError('Artifact selector is ambiguous in run', 409)
	index = matches[0]
	if (run['artifacts'][index].get('kind') == 'directory'):
		raise manager.PipelineError('Directory artifact download is not implemented', 409)
	return index


def open_run_artifact(db, owner, pipeline_id, node_id, run_ref,
		artifact_name=None, relative_path=None, retention_root=None):
	"""Open a unique registered file; caller must close the returned stream.

	Returns (fileobj, filename, mime). Does not use client paths for file opening.
	"""
	run = get_artifact_run(db, owner, pipeline_id, node_id, run_ref)
	index = find_artifact_index(run, artifact_name=artifact_name,
		relative_path=relative_path)
	return access.open_registered_artifact(
		db, owner, run, index, retention_root=retention_root
	)


def resolve_run_artifact(db, owner, pipeline_id, node_id, run_ref,
		artifact_name=None, relative_path=None, retention_root=None):
	"""Return an available artifact reference without disclosing server paths."""
	run = get_artifact_run(db, owner, pipeline_id, node_id, run_ref)
	index = find_artifact_index(run, artifact_name=artifact_name,
		relative_path=relative_path)
	fileobj, _, _ = access.open_registered_artifact(
		db, owner, run, index, retention_root=retention_root
	)
	fileobj.close()
	artifact = run['artifacts'][index]
	return {
		'pipeline_id': pipeline_id,
		'node_id': node_id,
		'run_id': run['run_id'],
		'run_name': run.get('run_name'),
		'job_id': run.get('job_id'),
		'artifact': {
			'index': index,
			'name': artifact.get('name'),
			'relative_path': artifact['relative_path'],
			'type': artifact.get('type', 'application/octet-stream'),
			'role': artifact.get('role', 'output'),
			'size_bytes': artifact.get('size_bytes')
		},
		'available': True
	}


def resolve_selected_artifact(db, owner, pipeline_id, node_id, artifact_name,
		retention_root=None):
	"""Backward-compatible selected-name resolver; uses the shared lookup."""
	return resolve_run_artifact(
		db, owner, pipeline_id, node_id, 'selected',
		artifact_name=artifact_name, retention_root=retention_root
	)

