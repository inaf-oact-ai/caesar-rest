"""Freeze retained upstream artifacts into downstream run metadata.

No scheduler operations, staging or writes to source artifacts.
"""
import re

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import access
from caesar_rest.pipeline.artifacts import retention
from caesar_rest import pipeline_directory_integrity as integrity

_INPUT = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
_SHA = re.compile(r'^[0-9a-f]{64}$')


def bind_inputs(db, owner, pipeline_id, requests, retention_root,
		max_directory_bytes=1024 * 1024 * 1024 * 1024,
		max_directory_entries=100000, max_directory_depth=16):
	"""Return immutable, owner-checked bindings for a new planned run.

	Each request has input_name, source_run_id, artifact_index.
	No client-supplied paths/checksums or implicit selection are accepted.
	"""
	if not isinstance(requests, list) or len(requests) > 32:
		raise manager.PipelineError('input_artifacts must be a list of at most 32 items', 400)
	bindings = []
	seen = set()
	for item in requests:
		if not isinstance(item, dict) or set(item) != {'input_name', 'source_run_id', 'artifact_index'}:
			raise manager.PipelineError('Invalid input artifact reference', 400)
		name = item['input_name']
		run_id = item['source_run_id']
		index = item['artifact_index']
		if not isinstance(name, str) or not _INPUT.fullmatch(name) or name in seen:
			raise manager.PipelineError('Invalid or duplicate input artifact name', 400)
		seen.add(name)
		if not isinstance(run_id, str) or not run_id or type(index) is not int or index < 0:
			raise manager.PipelineError('Invalid input artifact identity', 400)
		run = db.pipeline_runs.find_one({
			'owner': owner, 'pipeline_id': pipeline_id,
			'run_id': run_id, 'status': 'COMPLETED'
		})
		if run is None or not run.get('artifacts_registered_at'):
			raise manager.PipelineError('Upstream run is not completed or registered', 409)
		artifacts = run.get('artifacts') or []
		records = run.get('retained_artifacts')
		if index >= len(artifacts) or not isinstance(records, list) or len(records) != len(artifacts):
			raise manager.PipelineError('Upstream artifact is not retained', 409)
		artifact = artifacts[index]
		record = records[index]
		if not isinstance(artifact, dict) or not isinstance(record, dict) or record.get('index') != index:
			raise manager.PipelineError('Invalid upstream artifact metadata', 409)
		access._safe_parts(artifact.get('relative_path'))
		kind = artifact.get('kind', 'file')
		if kind not in ('file', 'directory') or type(artifact.get('size_bytes')) is not int:
			raise manager.PipelineError('Invalid upstream artifact kind or size', 409)
		if record.get('size_bytes') != artifact['size_bytes']:
			raise manager.PipelineError('Upstream artifact size mismatch', 409)
		if kind == 'directory':
			if record.get('kind') != 'directory':
				raise manager.PipelineError('Invalid retained directory metadata', 409)
			sha = record.get('manifest_sha256')
			if not isinstance(sha, str) or not _SHA.fullmatch(sha):
				raise manager.PipelineError('Invalid directory manifest digest', 409)
			base = retention.retained_directory(retention_root, owner, pipeline_id, run_id)
			try:
				verified = integrity.verify_directory_artifact(
					base, index, record, max_bytes=max_directory_bytes,
					max_entries=max_directory_entries, max_depth=max_directory_depth
				)
			except integrity.DirectoryIntegrityError as exc:
				raise manager.PipelineError('Upstream directory integrity verification failed', 409) from exc
			if verified.get('verified') is not True:
				raise manager.PipelineError('Upstream directory verification failed', 409)
			checksum_field = 'manifest_sha256'
		else:
			sha = record.get('sha256')
			if not isinstance(sha, str) or not _SHA.fullmatch(sha):
				raise manager.PipelineError('Invalid retained file digest', 409)
			fileobj, _, _ = access.open_registered_artifact(
				db, owner, run, index, retention_root=retention_root
			)
			fileobj.close()
			checksum_field = 'sha256'
		bindings.append({
			'input_name': name,
			'source_pipeline_id': pipeline_id,
			'source_node_id': run['node_id'],
			'source_run_id': run_id,
			'artifact_index': index,
			'artifact_name': artifact['name'],
			'artifact_kind': kind,
			'size_bytes': artifact['size_bytes'],
			checksum_field: sha
		})
	return bindings
