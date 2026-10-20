"""Stage frozen retained pipeline artifacts into a new private job input directory.

No client paths, no source mutation, and no MongoDB writes. Invoke only from a
trusted submission flow that owns the private, empty job workspace.
"""
import hashlib
import os
import re
import stat

from caesar_rest import pipeline_manager as manager
from caesar_rest import pipeline_artifact_retention as retention
from caesar_rest import pipeline_artifact_access as access
from caesar_rest import pipeline_directory_integrity as integrity
from caesar_rest import pipeline_directory_retention as directory_copy

_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
_SHA = re.compile(r'^[0-9a-f]{64}$')


def _check_binding(run, record, artifact, bound, index):
	if record.get('index') != index or bound.get('source_node_id') != run.get('node_id'):
		raise manager.PipelineError('Frozen artifact identity mismatch', 409)
	kind = artifact.get('kind', 'file')
	if (kind not in ('file', 'directory') or bound.get('artifact_kind') != kind
			or bound.get('artifact_name') != artifact.get('name')
			or type(artifact.get('size_bytes')) is not int
			or bound.get('size_bytes') != artifact['size_bytes']
			or record.get('size_bytes') != artifact['size_bytes']):
		raise manager.PipelineError('Frozen artifact metadata mismatch', 409)
	key = 'manifest_sha256' if kind == 'directory' else 'sha256'
	sha = record.get(key)
	if not isinstance(sha, str) or not _SHA.fullmatch(sha) or bound.get(key) != sha:
		raise manager.PipelineError('Frozen artifact checksum mismatch', 409)
	return kind


def stage_bound_inputs(db, owner, downstream_run, retention_root, job_workspace,
		max_file_bytes=1024 * 1024 * 1024,
		max_directory_bytes=1024 * 1024 * 1024 * 1024,
		max_directory_entries=100000, max_directory_depth=16):
	"""Return private staged input descriptors, with paths for trusted caller only.

	Workspace must already exist, be private, and have no inputs/ child.
	On any error, only newly created inputs/ is removed; retained sources stay intact.
	"""
	bindings = downstream_run.get('input_artifacts') or []
	if not isinstance(bindings, list) or len(bindings) > 32:
		raise manager.PipelineError('Invalid frozen input bindings', 409)
	if not bindings:
		return []
	if not isinstance(job_workspace, str) or not os.path.isabs(job_workspace):
		raise manager.PipelineError('Invalid private job workspace', 409)
	if any(type(v) is not int or v < 1 for v in
			(max_file_bytes, max_directory_bytes, max_directory_entries, max_directory_depth)):
		raise manager.PipelineError('Invalid staging limits', 503)
	# The trusted job creator must make the workspace with mode 0700.
	try:
		workspace_fd = directory_copy._open_directory(job_workspace)
		info = os.fstat(workspace_fd)
		if info.st_mode & 0o077:
			raise manager.PipelineError('Job workspace is not private', 409)
		os.mkdir('inputs', 0o700, dir_fd=workspace_fd)
		inputs_fd = os.open('inputs', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
			dir_fd=workspace_fd)
	except FileExistsError:
		raise manager.PipelineError('Staged inputs already exist', 409)
	except OSError as exc:
		raise manager.PipelineError('Cannot prepare private staging directory', 503) from exc
	finally:
		if 'workspace_fd' in locals():
			os.close(workspace_fd)
	inputs = os.path.join(job_workspace, 'inputs')
	results = []
	try:
		seen = set()
		for bound in bindings:
			if not isinstance(bound, dict):
				raise manager.PipelineError('Invalid frozen input record', 409)
			name = bound.get('input_name')
			if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen:
				raise manager.PipelineError('Invalid or duplicate staged input name', 409)
			seen.add(name)
			if bound.get('source_pipeline_id') != downstream_run.get('pipeline_id'):
				raise manager.PipelineError('Cross-pipeline artifact input rejected', 409)
			run_id = bound.get('source_run_id')
			index = bound.get('artifact_index')
			if (not isinstance(run_id, str) or type(index) is not int or index < 0
					or run_id not in downstream_run.get('input_runs', [])):
				raise manager.PipelineError('Invalid frozen source identity', 409)
			run = db.pipeline_runs.find_one({'owner': owner,
				'pipeline_id': downstream_run['pipeline_id'], 'run_id': run_id,
				'status': 'COMPLETED'})
			if run is None or not run.get('artifacts_registered_at'):
				raise manager.PipelineError('Frozen upstream run unavailable', 409)
			artifacts = run.get('artifacts') or []
			records = run.get('retained_artifacts')
			if (index >= len(artifacts) or not isinstance(records, list)
					or len(records) != len(artifacts)):
				raise manager.PipelineError('Frozen upstream artifact not retained', 409)
			artifact, record = artifacts[index], records[index]
			if not isinstance(artifact, dict) or not isinstance(record, dict):
				raise manager.PipelineError('Invalid upstream artifact record', 409)
			access._safe_parts(artifact.get('relative_path'))
			kind = _check_binding(run, record, artifact, bound, index)
			base = retention.retained_directory(retention_root, owner,
					downstream_run['pipeline_id'], run_id)
			destination = os.path.join(inputs, name)
			if kind == 'directory':
				try:
					integrity.verify_directory_artifact(base, index, record,
						max_bytes=max_directory_bytes,
						max_entries=max_directory_entries,
						max_depth=max_directory_depth)
					copied = directory_copy.copy_directory_artifact(
						os.path.join(base, '%04d' % index), destination, artifact,
						max_bytes=max_directory_bytes,
						max_entries=max_directory_entries,
						max_depth=max_directory_depth)
				except (integrity.DirectoryIntegrityError,
						directory_copy.DirectoryRetentionError) as exc:
					raise manager.PipelineError('Cannot safely stage retained directory', 409) from exc
				if copied['manifest_sha256'] != record['manifest_sha256']:
					raise manager.PipelineError('Staged directory digest mismatch', 409)
			else:
				if artifact['size_bytes'] > max_file_bytes:
					raise manager.PipelineError('Staged file exceeds limit', 413)
				source, _, _ = retention.open_retained_artifact(owner, run, index, retention_root)
				fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
					0o600, dir_fd=inputs_fd)
				count = 0
				digest = hashlib.sha256()
				with source, os.fdopen(fd, 'wb') as output:
					while True:
						block = source.read(1024 * 1024)
						if not block:
							break
						count += len(block)
						if count > artifact['size_bytes']:
							raise manager.PipelineError('Retained file changed during staging', 409)
						output.write(block)
						digest.update(block)
					output.flush()
					os.fsync(output.fileno())
				if count != artifact['size_bytes'] or digest.hexdigest() != record['sha256']:
					raise manager.PipelineError('Staged file checksum mismatch', 409)
			results.append({'input_name': name, 'kind': kind, 'private_path': destination,
				'source_run_id': run_id, 'artifact_index': index})
		os.fsync(inputs_fd)
		return results
	except BaseException:
		# Do not clean up an unknown hierarchy automatically. Caller owns the
		# newly created job workspace and can quarantine/delete it after failure.
		raise
	finally:
		os.close(inputs_fd)
