"""Generate an explicitly opt-in, preparation-only Slurm command.

Do NOT enable science execution with this module yet: the staged private input
paths are not passed to application-specific runners by this increment.
"""
import os
import shlex


def preparation_command(spec_path, workspace, runner_path, python_executable='/usr/bin/python3'):
	"""Return a shell-safe CLI command for a trusted spec in one workspace."""
	for label, value in (('spec_path', spec_path), ('workspace', workspace),
	                     ('runner_path', runner_path), ('python_executable', python_executable)):
		if not isinstance(value, str) or not os.path.isabs(value) or '\x00' in value or '\n' in value:
			raise ValueError('%s must be a clean absolute path' % label)
	if os.path.dirname(os.path.normpath(spec_path)) != os.path.normpath(workspace):
		raise ValueError('Spec must be placed in the job workspace')
	return ' '.join(shlex.quote(s) for s in (python_executable, runner_path,
	                                         '--spec', spec_path, '--workspace', workspace))


def preparation_script(spec_path, workspace, runner_path, python_executable='/usr/bin/python3'):
	"""Fail closed: preparation-only job; no Singularity call."""
	return '#!/bin/bash\nset -e\n' + preparation_command(
		spec_path, workspace, runner_path, python_executable
	) + '\n'


def build_preparation_job(manager, job_name, spec_path, workspace, runner_path,
					  python_executable='/usr/bin/python3'):
	"""Build a Slurm REST job payload; submit via existing manager.submit_job().

	All paths must refer to the *Slurm host*, not to the Flask container.
	No science executable is included. Caller reserves workspace and spec.
	"""
	import json
	if not isinstance(job_name, str) or not job_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in job_name):
		raise ValueError('Invalid job name')
	if manager.check_submit_vars() < 0:
		raise ValueError('Slurm manager is not configured')
	return json.dumps({
		'script': preparation_script(spec_path, workspace, runner_path, python_executable),
		'job': {
			'name': job_name,
			'environment': {'PATH': '/bin:/usr/bin/:/usr/local/bin/'},
			'current_working_directory': manager.cluster_batch_workdir,
			'cpus_per_task': 1,
			'tasks': 1,
		}
	})
