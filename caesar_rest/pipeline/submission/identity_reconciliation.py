"""Identity-aware, read-only Slurm evidence and opt-in conditional recovery.

Use a scheduler adapter exposing raw /jobs records, including Slurm job comment.
Do not call recovery automatically. No absent-job -> failed transition exists.
"""
import re

from caesar_rest.pipeline import manager

_TAG = re.compile(r'^caesar-v2:([0-9a-f]{32})$')


def attempt_comment(attempt_id):
	if not isinstance(attempt_id, str) or not re.fullmatch(r'[0-9a-f]{32}', attempt_id):
		raise manager.PipelineError('Invalid attempt identifier', 409)
	return 'caesar-v2:' + attempt_id


def verified_job_evidence(run, raw_jobs):
	"""Require one unique, exact comment match and valid Slurm job PID.

	Do not infer identity from job name or matching PID alone. Expects the
	unmodified `jobs` array from Slurm REST rather than simplified status.
	"""
	intent = run.get('submission_intent')
	if not isinstance(intent, dict):
		raise manager.PipelineError('Missing durable submission intent', 409)
	tag = attempt_comment(intent.get('attempt_id'))
	if not isinstance(raw_jobs, list):
		return None
	matches = [j for j in raw_jobs if isinstance(j, dict) and j.get('comment') == tag]
	if len(matches) != 1:
		return None
	job = matches[0]
	pid = job.get('job_id')
	if type(pid) is not int or pid <= 0:
		return None
	if run.get('scheduler_pid') is not None and run['scheduler_pid'] != pid:
		return None
	# A matching comment is Slurm identity evidence, not proof of a completed
	# scientific execution, nor permission to resubmit anything.
	return {'scheduler_pid': pid, 'comment': tag,
		'slurm_state': job.get('job_state') if isinstance(job.get('job_state'), str) else None}


def inspect_identity(db, owner, pipeline_id, node_id, run_id, raw_job_lookup):
	"""Read-only inspection; lookup must return raw Slurm REST job dictionaries."""
	manager.validate_identifier(node_id, 'node_id')
	manager.get_pipeline(owner, pipeline_id)
	run = db.pipeline_runs.find_one({'owner': owner, 'pipeline_id': pipeline_id,
		'node_id': node_id, 'run_id': run_id})
	if run is None:
		raise manager.PipelineError('Run not found', 404)
	if run.get('status') not in ('SUBMITTING', 'SUBMISSION_UNCERTAIN', 'SUBMITTED'):
		raise manager.PipelineError('Run cannot be reconciled', 409)
	attempt_comment((run.get('submission_intent') or {}).get('attempt_id'))
	try:
		jobs = raw_job_lookup()
	except Exception:
		jobs = None
	evidence = verified_job_evidence(run, jobs)
	return {'run_id': run_id, 'status': run['status'],
		'outcome': 'IDENTITY_CONFIRMED' if evidence else 'UNRESOLVED',
		'evidence': evidence, 'can_auto_retry': False}


def finalize_verified_submission(db, owner, pipeline_id, node_id, run_id, raw_job_lookup):
	"""Explicit, CAS-only recovery. Caller must be trusted administrative code.

	Never automatically invoked by route, monitor or background job. Conditional
	filter prevents stale evidence from changing an unrelated run. Does not
	consider absence evidence for failure.
	"""
	result = inspect_identity(db, owner, pipeline_id, node_id, run_id, raw_job_lookup)
	if result['outcome'] != 'IDENTITY_CONFIRMED':
		raise manager.PipelineError('Submission identity remains unresolved', 409)
	pid = result['evidence']['scheduler_pid']
	run = db.pipeline_runs.find_one({'owner': owner, 'pipeline_id': pipeline_id,
		'node_id': node_id, 'run_id': run_id})
	if run is None or run.get('status') not in ('SUBMITTING', 'SUBMISSION_UNCERTAIN'):
		raise manager.PipelineError('Run is not eligible for reconciliation', 409)
	intent = run.get('submission_intent')
	query = {'owner': owner, 'pipeline_id': pipeline_id, 'node_id': node_id,
		'run_id': run_id, 'status': run['status'],
		'submission_intent.attempt_id': intent['attempt_id'],
		'submission_intent.job_id': intent['job_id']}
	if run.get('scheduler_pid') is None:
		query['scheduler_pid'] = {'$exists': False} if 'scheduler_pid' not in run else None
	else:
		query['scheduler_pid'] = pid
	changed = db.pipeline_runs.update_one(query,
		{'$set': {'status': 'SUBMITTED', 'scheduler': 'slurm',
			'scheduler_pid': pid, 'job_id': intent['job_id'],
			'reconciled_at': manager.utcnow()},
		 '$unset': {'submission_token': ''}})
	if changed.modified_count != 1:
		raise manager.PipelineError('Concurrent reconciliation conflict', 409)
	return {'run_id': run_id, 'status': 'SUBMITTED', 'scheduler_pid': pid}
