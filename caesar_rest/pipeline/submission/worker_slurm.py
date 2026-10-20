"""Host-side Slurm commands for the job-local, versioned runtime archive."""
import os
import re
import shlex

from caesar_rest.pipeline.submission.worker_bundle import WORKER_NAME


def _absolute(value, label):
	if not isinstance(value, str) or not value.startswith('/') or '\x00' in value or '\r' in value or '\n' in value:
		raise ValueError('%s must be a clean absolute path' % label)
	if os.path.normpath(value) != value or '//' in value:
		raise ValueError('%s must be normalized' % label)
	return value


def worker_commands(workspace, staging_spec, execution_spec, worker_path, digest, python_executable='/usr/bin/python3'):
	"""Verify archive checksum before issuing either worker command.

	All paths are trusted server-side inputs, not unvalidated API parameters.
	"""
	ws = _absolute(workspace, 'workspace')
	py = _absolute(python_executable, 'python_executable')
	st = _absolute(staging_spec, 'staging_spec')
	ex = _absolute(execution_spec, 'execution_spec')
	worker = _absolute(worker_path, 'worker_path')
	if os.path.dirname(st) != ws or os.path.basename(st) != 'staging_spec.json':
		raise ValueError('Invalid staging spec location')
	if os.path.dirname(ex) != ws or os.path.basename(ex) != 'execution_spec.json':
		raise ValueError('Invalid execution spec location')
	if worker != os.path.join(ws, WORKER_NAME):
		raise ValueError('Invalid worker location')
	if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
		raise ValueError('Invalid worker digest')
	# Quote both file path and data; verify prior to executing the archive.
	verification = "printf '%s\\n' " + shlex.quote(digest + '  ' + worker) + ' | sha256sum -c --status -'
	prepare = shlex.join([py, worker, 'prepare', '--spec', st, '--workspace', ws])
	execute = shlex.join([py, worker, 'execute', '--spec', ex, '--workspace', ws])
	return verification, prepare, execute
