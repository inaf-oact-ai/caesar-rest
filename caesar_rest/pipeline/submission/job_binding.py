"""Associate generic pipeline runs with existing CAESAR-REST jobs.

This module does not submit or schedule work. It only reserves an individual
run and records the result of the ordinary job submission operation.
"""

import uuid
import re

from caesar_rest.pipeline import manager


class SubmissionClaim(object):
	"""A unique token for a single run submission attempt."""

	def __init__(self, owner, pipeline_id, run_id, token):
		self.owner = owner
		self.pipeline_id = pipeline_id
		self.run_id = run_id
		self.token = token


def claim_run(owner, pipeline_id, run_id, application, job_options, dataset_id=None,
		require_dataset_binding=False):		
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

	
	# - Require an immutable dataset binding for staged submissions.
	if require_dataset_binding:
		if (
			not isinstance(dataset_id, str)
			or not dataset_id
			or run.get('dataset_id') != dataset_id
		):
			raise manager.PipelineError(
				'Submitted dataset differs from the reserved pipeline input',
				409
			)

	elif run.get('dataset_id') is not None and run.get('dataset_id') != dataset_id:
		raise manager.PipelineError(
			'Submitted dataset differs from the reserved pipeline input',
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
	"""Record a failed or uncertain submission.

	An uncertain submission must never be automatically retried.
	Failure persistence must not silently succeed when no run is updated.
	"""
	_, runs, _ = manager.collections()

	status = (
		'SUBMISSION_UNCERTAIN'
		if uncertain else 'SUBMISSION_FAILED'
	)

	result = runs.update_one(
		{
			'owner': claim.owner,
			'pipeline_id': claim.pipeline_id,
			'run_id': claim.run_id,
			'submission_token': claim.token,
			'status': 'SUBMITTING'
		},
		{
			'$set': {
				'status': status,
				'submission_error': str(message),
				'job_id': job_id
			},
			'$unset': {
				'submission_token': ''
			}
		}
	)

	if result.modified_count != 1:
		raise manager.PipelineError(
			'Submission failure state could not be recorded; '
			'administrative reconciliation required',
			500
		)	

def begin_submission_intent(claim, assets):
	"""Atomically authorize exactly one V2 scheduler submission attempt.

	The intent is durable and is never automatically removed. An interrupted
	attempt requires reconciliation, not resubmission with the same claim.
	"""
	if not isinstance(claim, SubmissionClaim):
		raise manager.PipelineError('Invalid submission claim', 409)

	if not isinstance(assets, dict):
		raise manager.PipelineError('Invalid submission assets', 409)

	job_id = assets.get('job_id')
	digest = assets.get('worker_sha256')

	if (
		assets.get('version') != 2
		or assets.get('run_id') != claim.run_id
		or not isinstance(job_id, str)
		or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', job_id)
		or not isinstance(digest, str)
		or not re.fullmatch(r'[0-9a-f]{64}', digest)
	):
		raise manager.PipelineError('Invalid V2 submission identity', 409)

	intent = {
		'attempt_id': uuid.uuid4().hex,
		'job_id': job_id,
		'worker_sha256': digest,
		'created_at': manager.utcnow()
	}

	_, runs, _ = manager.collections()

	result = runs.update_one(
		{
			'owner': claim.owner,
			'pipeline_id': claim.pipeline_id,
			'run_id': claim.run_id,
			'status': 'SUBMITTING',
			'submission_token': claim.token,
			'submission_intent': {'$exists': False}
		},
		{
			'$set': {
				'submission_intent': intent
			}
		}
	)

	if result.modified_count != 1:
		raise manager.PipelineError(
			'Submission intent already recorded or claim is no longer active',
			409
		)

	return intent

