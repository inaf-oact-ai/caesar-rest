""" Describe existing per-job output workspace for pipeline runs.

This module does not copy, mount, chmod, or delete datasets. It only
validates and records the paths already assigned by CAESAR-REST.
"""

import os

from caesar_rest import pipeline_manager as manager


def workspace_for_job(job_top_dir, job_id):
	"""Return the existing unique output directory for a submitted job."""
	if not isinstance(job_id, str) or not job_id:
		raise ValueError('job_id must be a non-empty string')
	if '/' in job_id or '\\' in job_id or job_id in ('.', '..'):
		raise ValueError('Invalid job_id for workspace')
	if not os.path.isabs(job_top_dir):
		raise ValueError('job_top_dir must be absolute')
	return os.path.join(job_top_dir, 'job_' + job_id)


def record_workspace(owner, pipeline_id, run_id, job_id, job_top_dir):
	"""Record the already-created job workspace for the associated run.

	Only a SUBMITTED run with the matching job_id can be updated. This
	is metadata, not proof of read-only dataset isolation.
	"""
	path = workspace_for_job(job_top_dir, job_id)
	_, runs, _ = manager.collections()
	result = runs.update_one(
		{'owner': owner, 'pipeline_id': pipeline_id, 'run_id': run_id,
		 'job_id': job_id, 'status': 'SUBMITTED'},
		{'$set': {'workspace': {
			'path': path,
			'kind': 'existing_job_output',
			'input_isolation': 'not_guaranteed'
		}}}
	)
	return result.modified_count == 1
