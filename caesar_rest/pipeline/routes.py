"""Generic pipeline metadata endpoints; no agent decisions or job submission."""

from flask import current_app
from flask import Blueprint, jsonify, request, send_file
from werkzeug.exceptions import HTTPException
from caesar_rest import logger

from caesar_rest import utils
from caesar_rest import mongo
from caesar_rest.decorators import custom_require_login

from caesar_rest.pipeline import manager
from caesar_rest.pipeline import status as pipeline_status_sync
from caesar_rest.pipeline.artifacts import access as artifact_access
from caesar_rest.pipeline.artifacts import resolver as artifact_resolver
from caesar_rest.pipeline.artifacts import retention
from caesar_rest.pipeline.artifacts import directory_resolver

pipeline_bp = Blueprint('pipelines', __name__, url_prefix='/caesar/api/v1.0')

###########################################
###       HELPERS
###########################################
def invoke(callback, *args):
	"""Execute an authenticated pipeline operation with controlled errors."""

	try:
		owner = utils.get_storage_username()
		return callback(owner, *args)

	except manager.PipelineError as exc:
		return jsonify({
			'error': str(exc)
		}), exc.status

	except HTTPException:
		# Preserve Flask/Werkzeug HTTP handling, including 401/403/404.
		raise

	except Exception:
		logger.exception(
			'Unexpected pipeline API error',
			action='pipeline_api'
		)

		return jsonify({
			'error': 'internal_error',
			'error_description': 'An unexpected server error occurred'
		}), 500
		
def send_artifact_file(fileobj, filename, mime):
	"""Send a registered artifact with Flask 1.x/2.x compatibility."""

	try:
		return send_file(
			fileobj,
			as_attachment=True,
			download_name=filename,
			mimetype=mime
		)
	except TypeError as exc:
		# Retry only when the Flask API does not recognize download_name.
		if 'download_name' not in str(exc):
			raise

	return send_file(
		fileobj,
		as_attachment=True,
		attachment_filename=filename,
		mimetype=mime
	)

############################################
###      ROUTES
############################################
@pipeline_bp.route('/pipelines', methods=['POST'])
@custom_require_login
def create_pipeline():
	def action(owner):
		doc = manager.create_pipeline(owner, request.get_json(silent=True))
		return jsonify(doc), 201
	return invoke(action)


@pipeline_bp.route('/pipelines', methods=['GET'])
@custom_require_login
def list_pipelines():
	return invoke(lambda owner: jsonify(manager.list_pipelines(owner)))


@pipeline_bp.route('/pipelines/<pipeline_id>', methods=['GET'])
@custom_require_login
def get_pipeline(pipeline_id):
	return invoke(lambda owner: jsonify(manager.public_doc(manager.get_pipeline(owner, pipeline_id))))


#@pipeline_bp.route('/pipelines/<pipeline_id>/runs', methods=['GET'])
#@custom_require_login
#def list_runs(pipeline_id):
#	return invoke(lambda owner: jsonify(manager.list_runs(owner, pipeline_id)))

@pipeline_bp.route('/pipelines/<pipeline_id>/runs', methods=['GET', 'POST'])
@custom_require_login
def pipeline_runs(pipeline_id):

	if request.method == 'GET':
		return invoke(
			lambda owner: jsonify(manager.list_runs(owner, pipeline_id))
		)

	def action(owner):
		doc = manager.create_run_simple(
			owner,
			pipeline_id,
			request.get_json(silent=True),
			retention_root=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_ROOT'
			) or '',
			max_directory_bytes=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES',
				1024 * 1024 * 1024 * 1024
			),
			max_directory_entries=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES',
				100000
			),
			max_directory_depth=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH',
				16
			)
		)

		return jsonify(doc), 201

	return invoke(action)


@pipeline_bp.route(
	'/pipelines/<pipeline_id>/runs/<run_id>',
	methods=['GET']
)
@custom_require_login
def get_pipeline_run(pipeline_id, run_id):
	"""Return a run with scientific and artifact readiness metadata."""

	def action(owner):
		pipeline = manager.get_pipeline(owner, pipeline_id)

		run = mongo.db.pipeline_runs.find_one({
			'owner': owner,
			'pipeline_id': pipeline_id,
			'run_id': run_id
		})

		if run is None:
			raise manager.PipelineError('Run not found', 404)

		doc = manager.public_doc(run)

		doc['stage'] = (run.get('parameters') or {}).get('stage')

		readiness = manager.run_readiness(run)

		doc['artifacts_status'] = readiness['artifacts_status']
		doc['readiness'] = readiness['readiness']

		selections = pipeline.get('selections') or {}
		node_id = run.get('node_id')
		selection = selections.get(node_id) or {}

		doc['selected'] = (
			selection.get('run_id') == run_id
		)

		return jsonify(doc)

	return invoke(action)


@pipeline_bp.route(
	'/pipelines/<pipeline_id>/runs/<run_id>/submit',
	methods=['POST']
)
@custom_require_login
def submit_pipeline_run(pipeline_id, run_id):
	"""Submit a previously registered V2 run without repeated job options."""

	def action(owner):
		from caesar_rest.job_route import resolve_job_application
		from caesar_rest.pipeline.submission.v2_rest_submission import submit_v2

		payload = request.get_json(silent=True)

		if payload is None:
			payload = {}

		if not isinstance(payload, dict) or payload:
			raise manager.PipelineError(
				'Submission accepts an empty JSON object only',
				400
			)

		pipeline = manager.get_pipeline(owner, pipeline_id)

		run = mongo.db.pipeline_runs.find_one({
			'owner': owner,
			'pipeline_id': pipeline_id,
			'run_id': run_id
		})

		if run is None:
			raise manager.PipelineError('Run not found', 404)

		if run.get('status') != 'PLANNED':
			raise manager.PipelineError(
				'Only PLANNED runs can be submitted',
				409
			)

		# The run is immutable with respect to its execution identity.
		# Derive the complete legacy V2 request server-side.
		request_data = {
			'submission_version': 2,
			'app': run['application'],
			'pipeline_id': pipeline_id,
			'node_id': run['node_id'],
			'run_id': run_id,
			'job_options': run['parameters']
		}

		if pipeline.get('app') is not None:
			if run['application'] != pipeline['app']:
				raise manager.PipelineError(
					'Run application does not match pipeline',
					409
				)

		result = submit_v2(
			owner,
			request_data,
			resolve_job_application
		)

		result['pipeline_id'] = pipeline_id
		result['run_id'] = run_id

		return jsonify(result), 200

	return invoke(action)
	
	
@pipeline_bp.route('/pipelines/<pipeline_id>/nodes/<node_id>/runs', methods=['GET', 'POST'])
@custom_require_login
def node_runs(pipeline_id, node_id):
	
	if request.method == 'GET':
		return invoke(lambda owner: jsonify(manager.list_runs(owner, pipeline_id, node_id)))
		
	def action(owner):
		doc = manager.create_run(
			owner,
			pipeline_id,
			node_id,
			request.get_json(silent=True),
			retention_root=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_ROOT'
			) or '',
			max_directory_bytes=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES',
				1024 * 1024 * 1024 * 1024
			),
			max_directory_entries=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES',
				100000
			),
			max_directory_depth=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH',
				16
			)
		)
		return jsonify(doc), 201
		
	return invoke(action)


@pipeline_bp.route('/pipelines/<pipeline_id>/nodes/<node_id>/selection', methods=['POST'])
@custom_require_login
def select_run(pipeline_id, node_id):
	def action(owner):
		payload = request.get_json(silent=True)
		if not isinstance(payload, dict) or not isinstance(payload.get('run_id'), str):
			raise manager.PipelineError('run_id must be supplied as a string')
		return jsonify(manager.select_run(owner, pipeline_id, node_id, payload['run_id']))
	return invoke(action)
	
 
@pipeline_bp.route('/pipelines/<pipeline_id>/sync', methods=['POST'])
@custom_require_login
def sync_pipeline(pipeline_id):
	"""Explicitly synchronize associated pipeline runs with job states."""
	return invoke(lambda owner: jsonify(
		pipeline_status_sync.synchronize_pipeline(owner, pipeline_id)
	))
	
############################################
###      PIPELINE TREE
############################################
@pipeline_bp.route('/pipelines/<pipeline_id>/tree', methods=['GET'])
@custom_require_login
def get_pipeline_tree(pipeline_id):
	"""Return the logical hierarchy of an authenticated pipeline."""

	return invoke(
		lambda owner: jsonify(
			manager.get_pipeline_tree(owner, pipeline_id)
		)
	)
	
############################################
###      PIPELINE ARTIFACT LISTING
############################################
@pipeline_bp.route(
	'/pipelines/<pipeline_id>/nodes/<node_id>/runs/<run_id>/artifacts',
	methods=['GET']
)
@custom_require_login
def list_run_artifacts(pipeline_id, node_id, run_id):
	"""List registered artifacts belonging to an authenticated pipeline run."""

	def action(owner):
		run = artifact_access.get_run(
			mongo.db,
			owner,
			pipeline_id,
			node_id,
			run_id
		)

		return jsonify({
			'pipeline_id': pipeline_id,
			'node_id': node_id,
			'run_id': run_id,
			'artifacts': artifact_access.public_artifacts(run)
		})

	return invoke(action)
	
	
############################################
###      PIPELINE ARTIFACT DOWNLOAD
############################################
@pipeline_bp.route(
	'/pipelines/<pipeline_id>/nodes/<node_id>/runs/<run_id>/artifacts/<int:index>',
	methods=['GET']
)
@custom_require_login
def download_run_artifact(pipeline_id, node_id, run_id, index):
	"""Download one registered artifact from an authenticated pipeline run."""

	def action(owner):
		run = artifact_access.get_run(
			mongo.db,
			owner,
			pipeline_id,
			node_id,
			run_id
		)

		fileobj, filename, mime = artifact_access.open_registered_artifact(
			mongo.db,
			owner,
			run,
			index,
			retention_root=current_app.config.get('PIPELINE_ARTIFACT_RETENTION_ROOT')
		)

		try:
			return send_artifact_file(fileobj, filename, mime)
		except Exception:
			fileobj.close()
			raise

	return invoke(action)
	
############################################
###      PIPELINE ARTIFACT RESOLVE
############################################	
@pipeline_bp.route(
	'/pipelines/<pipeline_id>/nodes/<node_id>/selected/artifacts/<artifact_name>',
	methods=['GET']
)
@custom_require_login
def resolve_selected_artifact(pipeline_id, node_id, artifact_name):
	"""Resolve an available artifact of the selected upstream run."""

	return invoke(lambda owner: jsonify(
		artifact_resolver.resolve_selected_artifact(
			mongo.db,
			owner,
			pipeline_id,
			node_id,
			artifact_name,
			retention_root=current_app.config.get('PIPELINE_ARTIFACT_RETENTION_ROOT')
		)
	))
	
@pipeline_bp.route(
	'/pipelines/<pipeline_id>/nodes/<node_id>/selected/directories/<artifact_name>',
	methods=['GET']
)
@custom_require_login
def resolve_selected_directory(pipeline_id, node_id, artifact_name):
	"""Verify a selected retained directory; return identifiers, never paths."""

	def action(owner):
		return jsonify(directory_resolver.resolve_selected_directory(
			mongo.db,
			owner,
			pipeline_id,
			node_id,
			artifact_name,
			current_app.config.get('PIPELINE_ARTIFACT_RETENTION_ROOT') or '',
			max_entries=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES', 100000
			),
			max_bytes=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES',
				1024 * 1024 * 1024 * 1024
			),
			max_depth=current_app.config.get(
				'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH', 16
			)
		))

	return invoke(action)
	
############################################
###      PIPELINE ARTIFACT RETENTION
############################################
@pipeline_bp.route(
	'/pipelines/<pipeline_id>/nodes/<node_id>/runs/<run_id>/retain',
	methods=['POST']
)
@custom_require_login
def retain_run_artifacts(pipeline_id, node_id, run_id):
	"""Queue retention of a completed run without copying in this request."""

	def action(owner):
		run = artifact_access.get_run(
			mongo.db, owner, pipeline_id, node_id, run_id
		)

		if run.get('status') != 'COMPLETED':
			raise manager.PipelineError(
				'Pipeline run is not completed', 409
			)

		if not run.get('artifacts_registered_at') or not run.get('artifacts'):
			raise manager.PipelineError(
				'Pipeline artifacts are not registered', 409
			)

		if run.get('retained_artifacts') is not None:
			return jsonify({
				'run_id': run_id,
				'retention_status': 'READY',
				'already_retained': True
			}), 200

		status = run.get('retention_status', 'PENDING')

		if status == 'FAILED':
			raise manager.PipelineError(
				'Retention failed; inspect and recover partial artifacts '
				'before retrying', 409
			)

		if status == 'COPYING':
			return jsonify({
				'run_id': run_id,
				'retention_status': 'COPYING'
			}), 202

		result = mongo.db.pipeline_runs.update_one(
			{
				'_id': run['_id'],
				'owner': owner,
				'pipeline_id': pipeline_id,
				'node_id': node_id,
				'run_id': run_id,
				'status': 'COMPLETED',
				'retained_artifacts': {'$exists': False},
				'$or': [
					{'retention_status': {'$exists': False}},
					{'retention_status': 'PENDING'}
				]
			},
			{'$set': {'retention_status': 'PENDING'}}
		)

		if result.modified_count != 1:
			latest = mongo.db.pipeline_runs.find_one({
				'_id': run['_id']
			})
			if latest and latest.get('retained_artifacts') is not None:
				return jsonify({
					'run_id': run_id,
					'retention_status': 'READY'
				}), 200

		return jsonify({
			'run_id': run_id,
			'retention_status': 'PENDING',
			'message': 'Retention will be processed by the independent worker'
		}), 202

	return invoke(action)

