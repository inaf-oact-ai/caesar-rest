"""Generic pipeline metadata endpoints; no agent decisions or job submission."""

from flask import current_app
from flask import Blueprint, jsonify, request, send_file
from werkzeug.exceptions import HTTPException
from caesar_rest import logger

from caesar_rest import utils
from caesar_rest import mongo
from caesar_rest.decorators import custom_require_login
from caesar_rest import pipeline_manager as manager
from caesar_rest import pipeline_status_sync
from caesar_rest import pipeline_artifact_access as artifact_access
from caesar_rest import pipeline_artifact_resolver as artifact_resolver
from caesar_rest import pipeline_artifact_retention as retention

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


@pipeline_bp.route('/pipelines/<pipeline_id>/runs', methods=['GET'])
@custom_require_login
def list_runs(pipeline_id):
	return invoke(lambda owner: jsonify(manager.list_runs(owner, pipeline_id)))


@pipeline_bp.route('/pipelines/<pipeline_id>/nodes/<node_id>/runs', methods=['GET', 'POST'])
@custom_require_login
def node_runs(pipeline_id, node_id):
	if request.method == 'GET':
		return invoke(lambda owner: jsonify(manager.list_runs(owner, pipeline_id, node_id)))
	def action(owner):
		doc = manager.create_run(owner, pipeline_id, node_id, request.get_json(silent=True))
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
	
############################################
###      PIPELINE ARTIFACT RETENTION
############################################
@pipeline_bp.route(
	'/pipelines/<pipeline_id>/nodes/<node_id>/runs/<run_id>/retain',
	methods=['POST']
)
@custom_require_login
def retain_run_artifacts(pipeline_id, node_id, run_id):
	"""Copy registered artifacts into managed pipeline storage."""

	def action(owner):
		root = current_app.config.get(
			'PIPELINE_ARTIFACT_RETENTION_ROOT'
		) or ''

		limit = current_app.config.get(
			'PIPELINE_ARTIFACT_RETENTION_MAX_FILE_BYTES',
			1024 * 1024 * 1024
		)
		
		directory_bytes = current_app.config.get(
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES',
			1024 * 1024 * 1024 * 1024
		)

		directory_entries = current_app.config.get(
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES',
			100000
		)

		directory_depth = current_app.config.get(
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH',
			16
		)		

		return jsonify(retention.promote_run(
			mongo.db,
			owner,
			pipeline_id,
			node_id,
			run_id,
			root,
			limit,
			directory_bytes,
			directory_entries,
			directory_depth
		))

	return invoke(action)
