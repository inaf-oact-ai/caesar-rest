"""Resolve an artifact of a selected pipeline run without copying or staging it.

This is a point-in-time availability check, not a retention guarantee.
"""

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import access


def resolve_selected_artifact(db, owner, pipeline_id, node_id, artifact_name,
							  retention_root=None):
	"""Return a safe logical reference to a unique available selected artifact.

	Resolves the selection at request time. Downstream submissions must freeze
	the returned run_id and artifact path/index rather than re-resolving later.
	"""
	manager.validate_identifier(node_id, 'node_id')
	if not isinstance(artifact_name, str) or not artifact_name:
		raise manager.PipelineError('Invalid artifact name', 400)

	pipeline = manager.get_pipeline(owner, pipeline_id)
	selection = (pipeline.get('selections') or {}).get(node_id) or {}
	run_id = selection.get('run_id')
	if not isinstance(run_id, str) or not run_id:
		raise manager.PipelineError('No run selected for node', 409)

	run = access.get_run(db, owner, pipeline_id, node_id, run_id)
	if run.get('status') != 'COMPLETED':
		raise manager.PipelineError('Selected run is not completed', 409)
	if not run.get('artifacts_registered_at'):
		raise manager.PipelineError('Selected run artifacts not registered', 409)

	matches = [(i, artifact) for i, artifact in enumerate(run.get('artifacts') or [])
			   if artifact.get('name') == artifact_name]
	if not matches:
		raise manager.PipelineError('Artifact not found in selected run', 404)
	if len(matches) > 1:
		raise manager.PipelineError('Artifact name is ambiguous in selected run', 409)

	index, artifact = matches[0]
	# Reuse H1C's owner-scoped, symlink-resistant opening and size validation.
	# Close immediately; downstream staging must validate again when it runs.
	fileobj, _, _ = access.open_registered_artifact(
		db, owner, run, index, retention_root=retention_root
	)
	fileobj.close()

	return {
		'pipeline_id': pipeline_id,
		'node_id': node_id,
		'run_id': run_id,
		'run_name': run.get('run_name'),
		'job_id': run.get('job_id'),
		'artifact': {
			'index': index,
			'name': artifact_name,
			'relative_path': artifact['relative_path'],
			'type': artifact.get('type', 'application/octet-stream'),
			'role': artifact.get('role', 'output'),
			'size_bytes': artifact.get('size_bytes')
		},
		'available': True
	}
