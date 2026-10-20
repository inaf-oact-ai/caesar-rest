"""Read-only evidence gathering for uncertain V2 Slurm submissions.

A status lookup by scheduler PID cannot prove the full submission identity.
No database updates, scheduler submission, cancellation or automatic retry.
"""
import re

from caesar_rest import pipeline_manager as manager

_HEX = re.compile(r'^[0-9a-f]{32}$')
_SHA = re.compile(r'^[0-9a-f]{64}$')
_JOB = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
_STATES = {'SUBMITTING', 'SUBMISSION_UNCERTAIN', 'SUBMITTED'}


def inspect_v2_submission(db, owner, pipeline_id, node_id, run_id, slurm_manager):
	"""Inspect a run and query a known PID, returning evidence not a verdict.

	SlurmJobManager.get_job_status() returns a simplified job record with pid,
	state and status. It cannot attest to the CAESAR-REST attempt ID or job
	name; even a PID match must not trigger an automatic state transition.
	"""
	manager.validate_identifier(node_id, 'node_id')
	manager.get_pipeline(owner, pipeline_id)
	run = db.pipeline_runs.find_one({
		'owner': owner, 'pipeline_id': pipeline_id,
		'node_id': node_id, 'run_id': run_id
	})
	if run is None:
		raise manager.PipelineError('Pipeline run not found', 404)
	if run.get('status') not in _STATES:
		raise manager.PipelineError('Run is not in a reconcilable state', 409)
	intent = run.get('submission_intent')
	if not isinstance(intent, dict):
		raise manager.PipelineError('No V2 submission intent recorded', 409)
	if (not isinstance(intent.get('attempt_id'), str)
			or not _HEX.fullmatch(intent['attempt_id'])
			or not isinstance(intent.get('worker_sha256'), str)
			or not _SHA.fullmatch(intent['worker_sha256'])
			or not isinstance(intent.get('job_id'), str)
			or not _JOB.fullmatch(intent['job_id'])):
		raise manager.PipelineError('Invalid submission intent', 409)
	if run.get('job_id') not in (None, intent['job_id']):
		raise manager.PipelineError('Submission job identity mismatch', 409)

	result = {
		'run_id': run_id,
		'status': run['status'],
		'attempt_id': intent['attempt_id'],
		'job_id': intent['job_id'],
		'outcome': 'UNRESOLVED',
		'reason': 'No scheduler PID is recorded',
		'scheduler_evidence': None,
		'can_auto_retry': False,
		'can_auto_finalize': False
	}
	pid = run.get('scheduler_pid')
	if type(pid) is not int or pid <= 0:
		return result
	result['scheduler_pid'] = pid
	try:
		evidence = slurm_manager.get_job_status(str(pid))
	except Exception:
		result['reason'] = 'Scheduler lookup failed'
		return result
	if not isinstance(evidence, dict) or not evidence:
		result['reason'] = 'Scheduler returned no usable record'
		return result
	value = evidence.get('pid')
	if type(value) is int:
		match = value == pid
	elif isinstance(value, str) and value.isdigit():
		match = int(value) == pid
	else:
		match = False
	if not match:
		result['reason'] = 'Scheduler PID does not match recorded PID'
		return result
	state = evidence.get('state')
	if not isinstance(state, str):
		result['reason'] = 'Scheduler record has invalid state'
		return result
	result['scheduler_evidence'] = {'pid': pid, 'state': state}
	result['outcome'] = 'PID_FOUND'
	result['reason'] = 'Scheduler PID found; attempt identity not independently proven'
	return result
