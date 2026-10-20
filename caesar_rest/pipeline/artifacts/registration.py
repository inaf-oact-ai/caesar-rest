"""Register validated scientific results for completed staged pipeline runs.

The ordinary job and pipeline run records remain authoritative. This module
never changes job status or promotes a run to COMPLETED.
"""

import os

from caesar_rest.pipeline.artifacts import discovery
from caesar_rest.pipeline import manager
from caesar_rest.pipeline_workspace import workspace_for_job
from caesar_rest.job_configurator import JobConfigurator

class ArtifactRegistrationError(ValueError):
	pass


def register_completed_run(db, owner, pipeline_id, run_id, job_id, contract):
	"""Register owner-scoped artifacts for a completed staged-container job.

	Returns True on a new registration, False if no registration is applicable
	or if artifacts were already registered. Raises on invalid output/workspace.
	Caller should log errors without altering the scientific run status.
	"""
	if not all(isinstance(x, str) and x for x in (owner, pipeline_id, run_id, job_id)):
		raise ArtifactRegistrationError('Missing run identity')

	runs = db.pipeline_runs
	run_filter = {
		'owner': owner, 'pipeline_id': pipeline_id,
		'run_id': run_id, 'job_id': job_id, 'status': 'COMPLETED'
	}
	run = runs.find_one(run_filter)
	if run is None:
		return False
	if run.get('artifacts'):
		return False

	job = db[owner + '.jobs'].find_one({
		'job_id': job_id, 'pipeline_id': pipeline_id, 'run_id': run_id,
		'execution_mode': 'staged_container', 'app': run['application'],
		'state': 'SUCCESS'
	})
	if job is None:
		return False
	if str(job.get('exit_code')) != '0':
		return False

	job_top_dir = job.get('job_top_dir')
	if not isinstance(job_top_dir, str) or not os.path.isabs(job_top_dir):
		raise ArtifactRegistrationError('Invalid job top directory')
	# Use the trusted job directory derivation, never a user-supplied path.
	
	workspace = workspace_for_job(job_top_dir, job_id)
	if not os.path.isdir(workspace) or os.path.islink(workspace):
		raise ArtifactRegistrationError('Job workspace is missing or unsafe')
	if not isinstance(contract, dict) or not contract:
		raise ArtifactRegistrationError('Missing application output contract')

	artifacts = discovery.discover_artifacts(workspace, contract)
	if not artifacts:
		raise ArtifactRegistrationError('No scientific artifacts discovered')

	# Compare-and-set to prevent two sync workers from overwriting each other.
	result = runs.update_one(
		dict(run_filter, artifacts=[]),
		{'$set': {
			'artifacts': artifacts,
			'artifacts_registered_at': manager.utcnow(),
			'artifact_workspace': workspace
		}}
	)
	return result.modified_count == 1


def register_using_job_config(db, owner, pipeline_id, run_id, job_id):
	"""Resolve output definitions through the existing application registry."""
	run = db.pipeline_runs.find_one({
		'owner': owner, 'pipeline_id': pipeline_id,
		'run_id': run_id, 'job_id': job_id, 'status': 'COMPLETED'
	})
	if run is None:
		return False
	
	configurator = JobConfigurator()
	description = configurator.get_app_description(run['application'])
	if not isinstance(description, dict):
		raise ArtifactRegistrationError('Unknown application output contract')
	return register_completed_run(
		db, owner, pipeline_id, run_id, job_id,
		description.get('job_outputs') or {}
	)
