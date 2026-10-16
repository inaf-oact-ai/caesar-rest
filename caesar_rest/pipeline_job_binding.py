"""Associate generic pipeline runs with existing CAESAR-REST jobs.

This module does not submit or schedule work. It only reserves an individual
run and records the result of the ordinary job submission operation.
"""

import uuid

from caesar_rest import pipeline_manager as manager


class SubmissionClaim(object):
	"""A unique token for a single run submission attempt."""

	def __init__(self, owner, pipeline_id, run_id, token):
		self.owner = owner
		self.pipeline_id = pipeline_id
		self.run_id = run_id
		self.token = token


def claim_run(owner, pipeline_id, run_id, application, job_options):
	"""Claim a PLANNED run, preventing duplicate concurrent submission."""
	
	manager.get_pipeline(owner, pipeline_id)
	if not isinstance(run_id, str) or not run_id:
		raise manager.PipelineError('run_id is required')
	if not isinstance(job_options, dict):
		raise manager.PipelineError('job_options must be an object')

	_, runs, _ = manager.collections()
	query = {'owner': owner, 'pipeline_id': pipeline_id, 'run_id': run_id}
	run = runs.find_one(query)
	if run is None:
		raise manager.PipelineError('Pipeline run not found', 404)
	if run['application'] != application:
		raise manager.PipelineError('Application does not match reserved run', 409)

	# - Verify that the submitted options exactly match the reserved options.
	#   This prevents additional or modified scientific parameters.
	reserved_parameters = run.get('parameters', {})
	if reserved_parameters != job_options:
		raise manager.PipelineError(
			'Submission options differ from reserved run parameters',
			409
		)

	token = uuid.uuid4().hex
	claimed = runs.update_one(
		dict(query, status='PLANNED'),
		{'$set': {'status': 'SUBMITTING', 'submission_token': token}}
	)
	if claimed.modified_count != 1:
		raise manager.PipelineError('Run already claimed or submitted', 409)
	return SubmissionClaim(owner, pipeline_id, run_id, token)


def finish_submission(claim, job_id, scheduler, pid):
	"""Record a successful scheduler submission against the claimed run."""
	_, runs, _ = manager.collections()
	result = runs.update_one(
		{'owner': claim.owner, 'pipeline_id': claim.pipeline_id,
		 'run_id': claim.run_id, 'submission_token': claim.token,
		 'status': 'SUBMITTING'},
		{'$set': {'status': 'SUBMITTED', 'job_id': job_id,
		          'scheduler': scheduler, 'scheduler_pid': pid},
		 '$unset': {'submission_token': ''}}
	)
	if result.modified_count != 1:
		raise manager.PipelineError('Run submission record could not be finalized', 500)


def fail_submission(claim, message, uncertain=False, job_id=None):
	"""Record a failed submission, or an uncertain post-submission failure.

	An uncertain submission must never be treated as a safe automatic retry:
	the scheduler may already be running the job.
	"""
	_, runs, _ = manager.collections()
	status = 'SUBMISSION_UNCERTAIN' if uncertain else 'SUBMISSION_FAILED'
	runs.update_one(
		{'owner': claim.owner, 'pipeline_id': claim.pipeline_id,
		 'run_id': claim.run_id, 'submission_token': claim.token,
		 'status': 'SUBMITTING'},
		{'$set': {'status': status, 'submission_error': str(message),
		          'job_id': job_id}, '$unset': {'submission_token': ''}}
	)
