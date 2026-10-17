"""Reconcile pipeline run status with the existing CAESAR-REST job records.

This module never queries Slurm, submits jobs, or updates standalone jobs.
It reads the owner's ordinary MongoDB job collection and updates only
associated pipeline runs. Invoke explicitly via the pipeline sync endpoint.
"""

from caesar_rest import mongo
from caesar_rest import pipeline_manager as manager

# Match the persisted job states used by the existing job monitoring API.
ACTIVE_STATES = {'STARTED', 'RUNNING'}
SUCCESS_STATES = {'SUCCESS'}
FAILURE_STATES = {'FAILURE', 'TIMED-OUT', 'TIMEOUT', 'ABORTED'}
CANCEL_STATES = {'CANCELED', 'CANCELLED'}


def desired_status(job):
	"""Return pipeline status or None when the job is not terminal/known."""
	state = str(job.get('state') or '').upper()
	if state in ACTIVE_STATES:
		return 'RUNNING'
	if state in SUCCESS_STATES:
		# A success status with an explicitly nonzero exit code is not success.
		exit_code = job.get('exit_code')
		if exit_code is not None and str(exit_code) not in ('0', ''):
			return 'FAILED'
		return 'COMPLETED'
	if state in FAILURE_STATES:
		return 'FAILED'
	if state in CANCEL_STATES:
		return 'CANCELLED'
	return None


def synchronize_monitored_job(db, job_obj, state, exit_code=None):
	"""Synchronize one pipeline run after its ordinary job DB update.

	This function does not query the scheduler or modify the job record.
	Standalone jobs are ignored.
	"""

	pipeline_id = job_obj.get('pipeline_id')
	run_id = job_obj.get('run_id')
	job_id = job_obj.get('job_id')

	if not pipeline_id or not run_id or not job_id:
		return False

	# - Use the same mapping as explicit M1C synchronization.
	job_state = {'state': state, 'exit_code': exit_code}
	status = desired_status(job_state)
	if status is None:
		return False

	# - Never regress RUNNING to SUBMITTED, or overwrite
	#   a terminal run. The conditional update is atomic.
	allowed_states = ['SUBMITTED']
	if status != 'RUNNING':
		allowed_states.append('RUNNING')

	changes = {
		'status': status,
		'job_state': state,
		'job_exit_code': exit_code,
		'synchronized_at': manager.utcnow()
	}

	if status in ('COMPLETED', 'FAILED', 'CANCELLED'):
		changes['finished_at'] = manager.utcnow()

	# - Derive the owner from the existing per-user job collection
	#   in the caller, not from client-supplied pipeline metadata.
	owner = job_obj.get('_pipeline_sync_owner')
	if not owner:
		return False

	result = db.pipeline_runs.update_one(
		{
			'owner': owner,
			'pipeline_id': pipeline_id,
			'run_id': run_id,
			'job_id': job_id,
			'status': {'$in': allowed_states}
		},
		{'$set': changes}
	)

	return result.modified_count == 1


def synchronize_pipeline(owner, pipeline_id):
	"""Refresh known associated runs using already persisted job states.

	Owner-scoped; monotonic; terminal pipeline states are not overwritten.
	Uncertain or incomplete submission records are deliberately excluded.
	"""
	manager.get_pipeline(owner, pipeline_id)
	_, runs, _ = manager.collections()
	jobs = mongo.db[owner + '.jobs']
	query = {
		'owner': owner,
		'pipeline_id': pipeline_id,
		'status': {'$in': ['SUBMITTED', 'RUNNING']},
		'job_id': {'$type': 'string'}
	}
	updated = []
	missing_jobs = []
	unchanged = 0
	for run in runs.find(query):
		job_id = run['job_id']
		job = jobs.find_one({
			'job_id': job_id,
			'pipeline_id': pipeline_id,
			'run_id': run['run_id']
		})
		if job is None:
			missing_jobs.append(run['run_id'])
			continue
		status = desired_status(job)
		if status is None or (run['status'] == 'RUNNING' and status == 'RUNNING'):
			unchanged += 1
			continue
		# A delayed PENDING state cannot regress a RUNNING run. The
		# conditional update also prevents overwriting completed runs.
		filter_doc = {
			'_id': run['_id'], 'owner': owner, 'pipeline_id': pipeline_id,
			'run_id': run['run_id'], 'job_id': job_id,
			'status': {'$in': ['SUBMITTED', 'RUNNING']}
		}
		changes = {
			'status': status,
			'job_state': str(job.get('state') or ''),
			'job_exit_code': job.get('exit_code'),
			'synchronized_at': manager.utcnow()
		}
		if status in ('COMPLETED', 'FAILED', 'CANCELLED'):
			changes['finished_at'] = manager.utcnow()
		result = runs.update_one(filter_doc, {'$set': changes})
		if result.modified_count:
			updated.append({'run_id': run['run_id'], 'job_id': job_id, 'status': status})
		else:
			unchanged += 1
	return {'pipeline_id': pipeline_id, 'updated': updated,
		'missing_job_run_ids': missing_jobs, 'unchanged': unchanged}
