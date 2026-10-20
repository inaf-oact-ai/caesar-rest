"""Claimed V2 job submission through an injected trusted Slurm client.

The caller supplies validated server configuration and arguments, never client
supplied paths or shell commands. No REST endpoint is added by this module.
"""
import json
import re

from caesar_rest import pipeline_manager as manager
from caesar_rest.pipeline.submission import job_binding as binding
from caesar_rest import pipeline_v2_claimed_preparation as preparation
from caesar_rest import pipeline_worker_slurm as worker_slurm
from caesar_rest.pipeline_v2_identity_reconciliation import attempt_comment

_JOB_NAME = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def build_v2_slurm_payload(assets, job_name, batch_workdir, cpus_per_task=1,
		tasks=1, python_executable='/usr/bin/python3'):
	"""Return a single sequential prepare/execute Slurm REST payload.

	Both steps run only after verifying the isolated worker checksum. Failure
	of prepare stops execution via the shell's errexit flag.
	"""
	if not isinstance(assets, dict) or assets.get('version') != 2:
		raise manager.PipelineError('Invalid V2 preparation assets', 409)
	if not isinstance(job_name, str) or not _JOB_NAME.fullmatch(job_name):
		raise manager.PipelineError('Invalid V2 Slurm job name', 409)
	if (not isinstance(batch_workdir, str) or not batch_workdir.startswith('/')
			or '\x00' in batch_workdir or '\n' in batch_workdir or '\r' in batch_workdir):
		raise manager.PipelineError('Invalid batch working directory', 503)
	if type(cpus_per_task) is not int or cpus_per_task < 1 or type(tasks) is not int or tasks < 1:
		raise manager.PipelineError('Invalid Slurm resource request', 409)
	try:
		verify, prepare, execute = worker_slurm.worker_commands(
			assets['workspace_cluster'], assets['staging_spec_cluster'],
			assets['execution_spec_cluster'], assets['worker_cluster'],
			assets['worker_sha256'], python_executable=python_executable)
	except (KeyError, ValueError, TypeError) as exc:
		raise manager.PipelineError('Invalid V2 worker assets', 409) from exc
	return json.dumps({
		'script': '#!/bin/bash\nset -e\n' + verify + '\n' + prepare + '\n' + execute + '\n',
		'job': {
			'name': job_name,
			'environment': {'PATH': '/bin:/usr/bin/:/usr/local/bin/'},
			'current_working_directory': batch_workdir,
			'cpus_per_task': cpus_per_task,
			'tasks': tasks
		}
	})


def _scheduler_result(reply):
	"""Return (pid, rejected) from the Slurm REST response.

	Unknown / malformed results are uncertain, not definite rejections.
	"""
	if not isinstance(reply, dict):
		return None, False
	pid = reply.get('job_id')
	if type(pid) is int and pid > 0 and not reply.get('errors'):
		return pid, False
	# A documented explicit error response with no valid job id rejects the job.
	if reply.get('errors') and isinstance(reply['errors'], list) and not (type(pid) is int and pid > 0):
		return None, True
	return None, False



def submit_claimed_v2(prepared, slurm_manager, job_name, cpus_per_task=1,
		tasks=1, python_executable='/usr/bin/python3'):
	"""Submit one claimed V2 run using a durable, one-shot intent.

	The intent must be recorded before contacting the scheduler.
	A duplicate invocation never contacts Slurm.
	"""
	if not isinstance(prepared, dict):
		raise manager.PipelineError('Invalid claimed preparation', 409)

	claim = prepared.get('claim')
	assets = prepared.get('assets')

	if not isinstance(claim, binding.SubmissionClaim):
		raise manager.PipelineError('Missing submission claim', 409)

	if not isinstance(assets, dict) or assets.get('run_id') != claim.run_id:
		raise manager.PipelineError('Claim and assets do not match', 409)

	# Complete all local validation before consuming the one-shot intent.
	# Preflight failure leaves the run SUBMITTING for explicit investigation.
	try:
		if slurm_manager.check_submit_vars() < 0:
			raise manager.PipelineError('Slurm is not configured', 503)

		payload = build_v2_slurm_payload(
			assets,
			job_name,
			slurm_manager.cluster_batch_workdir,
			cpus_per_task=cpus_per_task,
			tasks=tasks,
			python_executable=python_executable
		)
	except manager.PipelineError:
		raise
	except Exception as exc:
		raise manager.PipelineError(
			'V2 scheduler payload preparation failed', 503
		) from exc

	# Atomically consume the one-shot submission intent.
	# Duplicate attempts are rejected here, before contacting Slurm.
	intent = binding.begin_submission_intent(claim, assets)

	# The scheduler has not been contacted yet.
	# Any failure here is a definite local preparation failure.
	try:
		prepared_payload = json.loads(payload)

		prepared_payload['job']['comment'] = attempt_comment(
			intent['attempt_id']
		)

		payload = json.dumps(prepared_payload)

	except Exception as exc:
		# The intent remains consumed permanently.
		# Never revert this run to PLANNED or automatically retry.
		try:
			binding.fail_submission(
				claim,
				'V2 submission payload finalization failed',
				uncertain=False,
				job_id=assets.get('job_id')
			)
		except Exception as persistence_exc:
			raise manager.PipelineError(
				'V2 payload finalization and failure recording failed; '
				'administrative reconciliation required',
				503
			) from persistence_exc

		raise manager.PipelineError(
			'V2 submission payload finalization failed',
			503
		) from exc

	# No automatic retry is permitted after this point.
	try:
		reply = slurm_manager.submit_job(payload)
	except Exception as exc:
		binding.fail_submission(
			claim,
			'Slurm submission outcome unknown',
			uncertain=True,
			job_id=assets.get('job_id')
		)
		raise manager.PipelineError(
			'Slurm submission outcome uncertain', 503
		) from exc

	pid, rejected = _scheduler_result(reply)

	if pid is None:
		binding.fail_submission(
			claim,
			'Slurm explicitly rejected submission'
			if rejected else 'Slurm submission outcome unknown',
			uncertain=not rejected,
			job_id=assets.get('job_id')
		)

		raise manager.PipelineError(
			'Slurm rejected submission'
			if rejected else 'Slurm submission outcome uncertain',
			409 if rejected else 503
		)

	try:
		binding.finish_submission(
			claim,
			assets['job_id'],
			'slurm',
			pid
		)
	except Exception as exc:
		# The scheduler may already be running this job.
		# Preserve the intent and require reconciliation.
		binding.fail_submission(
			claim,
			'Scheduler accepted job; database finalization uncertain',
			uncertain=True,
			job_id=assets['job_id']
		)

		raise manager.PipelineError(
			'Job accepted but persistence uncertain', 503
		) from exc

	return {
		'run_id': claim.run_id,
		'job_id': assets['job_id'],
		'scheduler': 'slurm',
		'scheduler_pid': pid,
		'status': 'SUBMITTED'
	}

