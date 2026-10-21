"""H2C2b2a: build trusted V2 specifications from frozen upstream artifacts.

No REST route, filesystem writes, Slurm submission or client-supplied paths.
The caller supplies server-configured retention roots for the API and Slurm
hosts. Returned specs are point-in-time verified; H2C2b2b must protect the
source against changes during worker staging and verify the private copies.
"""
import os
import re
import hashlib
import json

from caesar_rest.pipeline import manager
from caesar_rest import dataset_registry
from caesar_rest.pipeline.staging.submission_specs import (
	_translate,
	PipelineSubmissionError
)
from caesar_rest.pipeline.artifacts import binding
from caesar_rest.pipeline.artifacts import retention
from caesar_rest.pipeline.staging import multi_input_specs as specs
from caesar_rest.pipeline.artifacts.directory_retention import _open_directory

_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')


def _root(value):
	if (not isinstance(value, str) or not os.path.isabs(value)
			or value == '/' or os.path.normpath(value) != value
			or '//' in value or any(p in ('.', '..') for p in value.split('/'))):
		raise manager.PipelineError('Invalid configured retention root', 503)
	return value


def _safe_directory(path):
	"""Require a traversable directory with no symlink path components."""
	try:
		fd = _open_directory(path)
		os.close(fd)
	except (OSError, ValueError) as exc:
		raise manager.PipelineError('Unsafe or unavailable retained directory', 409) from exc

def build_bound_v2_specs(db, owner, downstream_run, retention_root_app,
		retention_root_cluster, workspace_cluster, image, arguments, input_options,
		max_directory_bytes=1024 * 1024 * 1024 * 1024,
		max_directory_entries=100000, max_directory_depth=16,
		submission_token=None,
		dataset_app_root=None,
		dataset_cluster_root=None,
		dataset_input_name='measurement_set'):
	"""Revalidate immutable bindings and return a trusted staging/execution pair.

	``downstream_run`` must come from an owner-scoped DB lookup, never raw JSON.
	All roots, image, arguments, and option mappings must be server-generated.
	"""
	if not isinstance(downstream_run, dict) or downstream_run.get('owner') != owner:
		raise manager.PipelineError('Invalid downstream run ownership', 403)
	
	pipeline_id = downstream_run.get('pipeline_id')
	run_id = downstream_run.get('run_id')
	node_id = downstream_run.get('node_id')
	if not all(isinstance(x, str) and x for x in (pipeline_id, run_id, node_id)):
		raise manager.PipelineError('Invalid downstream run identity', 409)
	
	if submission_token is None:
		if downstream_run.get('status') != 'PLANNED':
			raise manager.PipelineError('Downstream run is not PLANNED', 409)
	else:
		if (
			not isinstance(submission_token, str)
			or not re.fullmatch(r'[0-9a-f]{32}', submission_token)
			or downstream_run.get('status') != 'SUBMITTING'
			or downstream_run.get('submission_token') != submission_token
		):
			raise manager.PipelineError('Downstream submission claim mismatch', 409)	
		
	manager.get_pipeline(owner, pipeline_id)
	
	stored = downstream_run.get('input_artifacts')
	if not isinstance(stored, list):
		raise manager.PipelineError('Invalid frozen inputs', 409)

	dataset_id = downstream_run.get('dataset_id')

	if not stored and dataset_id is None:
		raise manager.PipelineError('V2 run has no inputs', 409)

	if len(stored) + int(dataset_id is not None) > 32:
		raise manager.PipelineError('Too many V2 inputs', 409)	
		
	if not isinstance(downstream_run.get('input_runs'), list):
		raise manager.PipelineError('Downstream parent runs are invalid', 409)
	
	request = []
	for item in stored:
		if not isinstance(item, dict):
			raise manager.PipelineError('Invalid frozen input', 409)
		if item.get('source_pipeline_id') != pipeline_id:
			raise manager.PipelineError('Cross-pipeline input not supported', 409)
		if item.get('source_run_id') not in downstream_run['input_runs']:
			raise manager.PipelineError('Frozen input not in parent runs', 409)
		name = item.get('input_name')
		if not isinstance(name, str) or not _NAME.fullmatch(name):
			raise manager.PipelineError('Invalid frozen input name', 409)
		request.append({'input_name': name, 'source_run_id': item.get('source_run_id'),
			'artifact_index': item.get('artifact_index')})
			
	inputs = []

	if stored:
		app_root = _root(retention_root_app)
		cluster_root = _root(retention_root_cluster)

		# - Preserve existing frozen artifact verification.
		verified = binding.bind_inputs(
			db, owner, pipeline_id, request, app_root,
			max_directory_bytes=max_directory_bytes,
			max_directory_entries=max_directory_entries,
			max_directory_depth=max_directory_depth
		)

		if verified != stored:
			raise manager.PipelineError(
				'Frozen artifact identity or checksum changed', 409
			)
	else:
		verified = []

	# - Add a registered dataset as a trusted read-only reference.
	if dataset_id is not None:
		if (
			not isinstance(dataset_input_name, str)
			or not _NAME.fullmatch(dataset_input_name)
			or dataset_input_name in {
				item['input_name'] for item in verified
			}
		):
			raise manager.PipelineError(
				'Invalid or conflicting dataset input name', 409
			)

		if not dataset_app_root or not dataset_cluster_root:
			raise manager.PipelineError(
				'Dataset storage roots are not configured', 503
			)

		try:
			source_app = dataset_registry.resolve_input_dataset(dataset_id)

			if not os.path.isdir(source_app):
				raise manager.PipelineError(
					'V2 reference dataset must be a directory', 409
				)

			_safe_directory(source_app)

			source_cluster = _translate(
				source_app,
				dataset_app_root,
				dataset_cluster_root
			)

		except dataset_registry.DatasetError as exc:
			raise manager.PipelineError(
				str(exc), exc.status
			) from exc

		except PipelineSubmissionError as exc:
			raise manager.PipelineError(
				'Invalid dataset storage mapping', 409
			) from exc

		inputs.append({
			'input_name': dataset_input_name,
			'source': source_cluster,
			'mode': 'reference_ro'
		})	
	
	
	
	for item in verified:
		base = retention.retained_directory(app_root, owner, pipeline_id,
			item['source_run_id'])
		_safe_directory(base)
		index = item['artifact_index']
		relative = os.path.relpath(base, app_root)
		source_app = os.path.join(base, '%04d' % index)
		if item['artifact_kind'] == 'directory':
			_safe_directory(source_app)
		else:
			# File integrity was verified by bind_inputs() through the existing
			# safe retained-file opener. No path or client checksum is trusted.
			if not os.path.isfile(source_app) or os.path.islink(source_app):
				raise manager.PipelineError('Retained file unavailable', 409)
		source_cluster = os.path.join(cluster_root, relative, '%04d' % index)
		
		entry = {
			'input_name': item['input_name'],
			'source': source_cluster,
			'kind': item['artifact_kind'],
			'size_bytes': item['size_bytes']
		}

		if item['artifact_kind'] == 'file':
			entry['sha256'] = item['sha256']
		else:
			from caesar_rest.pipeline.artifacts.directory_integrity import _read_sidecar

			try:
				data = _read_sidecar(
					base,
					'%04d.manifest.json' % index,
					32 * 1024 * 1024
				)

				if hashlib.sha256(data).hexdigest() != item['manifest_sha256']:
					raise ValueError('Directory manifest changed')

				manifest = json.loads(data.decode('utf-8'))
				entry['manifest_entries'] = manifest['entries']

			except (OSError, ValueError, KeyError, TypeError) as exc:
				raise manager.PipelineError(
					'Cannot freeze trusted directory manifest', 409
				) from exc

		inputs.append(entry)
		
	try:
		return specs.build_multi_input_specs(workspace_cluster, inputs, image,
			arguments, input_options)
	except specs.MultiInputSpecError as exc:
		raise manager.PipelineError('Invalid trusted V2 submission specification', 409) from exc
		
		
