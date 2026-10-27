"""Owner-scoped read-only resolution of a retained pipeline directory.

No client-controlled filesystem paths, no staging, and no mutation.
A verification result is a point-in-time check, not a durable open handle.
"""

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import access
from caesar_rest.pipeline.artifacts import retention
from caesar_rest.pipeline.artifacts import directory_integrity as integrity

def resolve_selected_directory(db, owner, pipeline_id, node_id, artifact_name,
		retention_root, max_entries=100000,
		max_bytes=1024 * 1024 * 1024 * 1024, max_depth=16):
	"""Verify the unique retained directory on the selected completed run."""
	manager.validate_identifier(node_id, 'node_id')
	if not isinstance(artifact_name, str) or not artifact_name:
		raise manager.PipelineError('Invalid artifact name', 400)

	pipeline = manager.get_pipeline(owner, pipeline_id)
	selection = (pipeline.get('selections') or {}).get(node_id) or {}
	run_id = selection.get('run_id')
	if not isinstance(run_id, str) or not run_id:
		raise manager.PipelineError('No run selected for node', 409)

	run = access.get_run(db, owner, pipeline_id, node_id, run_id)
	if run.get('status') != 'COMPLETED' or not run.get('artifacts_registered_at'):
		raise manager.PipelineError('Selected run artifacts unavailable', 409)

	matches = [(i, a) for i, a in enumerate(run.get('artifacts') or [])
		if a.get('name') == artifact_name]
	if not matches:
		raise manager.PipelineError('Artifact not found in selected run', 404)
	if len(matches) != 1:
		raise manager.PipelineError('Artifact name is ambiguous in selected run', 409)

	index, artifact = matches[0]
	if artifact.get('kind', 'file') != 'directory':
		raise manager.PipelineError('Selected artifact is not a directory', 409)
	# Check registered path syntax even though no filesystem path is returned.
	access._safe_parts(artifact.get('relative_path'))
	records = run.get('retained_artifacts')
	if not isinstance(records, list) or len(records) != len(run.get('artifacts') or []):
		raise manager.PipelineError('Directory artifact is not retained', 409)
	record = records[index]
	if not isinstance(record, dict) or record.get('kind') != 'directory':
		raise manager.PipelineError('Directory retention record is invalid', 409)
	for field in ('size_bytes', 'file_count', 'directory_count'):
		if record.get(field) != artifact.get(field):
			raise manager.PipelineError('Directory retention metadata mismatch', 409)

	base = retention.retained_directory(retention_root, owner, pipeline_id, run_id)
	try:
		verified = integrity.verify_directory_artifact(
			base, index, record, max_entries=max_entries,
			max_bytes=max_bytes, max_depth=max_depth
		)
	except integrity.DirectoryIntegrityError as exc:
		raise manager.PipelineError('Retained directory verification failed', 409) from exc

	if verified.get('verified') is not True:
		raise manager.PipelineError('Retained directory verification failed', 409)

	return {
		'pipeline_id': pipeline_id,
		'node_id': node_id,
		'run_id': run_id,
		'run_name': run.get('run_name'),
		'job_id': run.get('job_id'),
		'artifact': {
			'index': index,
			'name': artifact_name,
			'kind': 'directory',
			'relative_path': artifact['relative_path'],
			'type': artifact.get('type') or 'application/octet-stream',
			'role': artifact.get('role') or 'output',
			'size_bytes': record['size_bytes'],
			'file_count': record['file_count'],
			'directory_count': record['directory_count'],
			'manifest_sha256': record['manifest_sha256']
		},
		'available': True,
		'retained': True
	}
