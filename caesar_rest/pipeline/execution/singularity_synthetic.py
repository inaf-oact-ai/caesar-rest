"""Trusted, fixed synthetic Singularity consumer of staged private inputs.

Host-side Python needs caesar_rest; the test image only needs /bin/sh.
This is not an arbitrary command executor and must not be exposed to REST clients.
"""
import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from pipeline_runtime.staging import StagingError
from pipeline_runtime.resolver import resolve_staged_inputs
from pipeline_runtime.paths import map_staged_inputs, map_host_path


# A fixed program executed IN the container. Positional parameters are paths,
# passed as argv (not interpolated into shell source).
_SYNTHETIC_SH = r'''set -eu
[ "$(cat "$1")" = "test fits" ] || exit 31
[ "$(cat "$2/data")" = "test table" ] || exit 32
[ ! -e "$3" ] || exit 33
printf 'synthetic container changed private table\n' > "$2/data"
printf '{"status":"EXECUTED_IN_CONTAINER"}\n' > "$3"
printf 'SINGULARITY_SYNTHETIC_OK\n'
'''


def _clean_abs(value, label):
	if not isinstance(value, str) or not value.startswith('/') or any(c in value for c in ('\x00', '\n', '\r')):
		raise ValueError('%s must be a clean absolute path' % label)
	if any(part in ('.', '..') for part in value.split('/')) or '//' in value or (value != '/' and value.endswith('/')):
		raise ValueError('%s must be a normalized path' % label)
	return value


def singularity_synthetic_command(workspace, image, container_workspace, runner_path,
		python_executable='/usr/bin/python3'):
	"""Build host-side shell-safe invocation for the fixed wrapper."""
	values = (python_executable, runner_path, workspace, image, container_workspace)
	for name, value in zip(('python_executable', 'runner_path', 'workspace', 'image', 'container_workspace'), values):
		_clean_abs(value, name)
	return ' '.join(shlex.quote(s) for s in (
		python_executable, runner_path, '--workspace', workspace, '--image', image,
		'--container-workspace', container_workspace
	))


def execute(workspace, image, container_workspace, runner=subprocess.run):
	"""Resolve READY inputs and run immutable synthetic command in container."""
	_clean_abs(workspace, 'workspace')
	_clean_abs(image, 'image')
	_clean_abs(container_workspace, 'container_workspace')
	if container_workspace == '/':
		raise ValueError('Container workspace cannot be /')
	base = Path(workspace)
	if base.is_symlink() or not base.is_dir():
		raise StagingError('Private workspace missing or symlinked')
	# Do not let callers substitute a different workspace through a symlink.
	if str(base.resolve(strict=True)) != workspace:
		raise StagingError('Workspace path is not canonical')
	if not Path(image).is_file() or Path(image).is_symlink():
		raise StagingError('Trusted Singularity image is missing or symlinked')
	paths = resolve_staged_inputs(workspace, required_names=['image.fits', 'solutions.tbl'])
	binds = [{'source': workspace, 'destination': container_workspace}]
	mapped = map_staged_inputs(paths, workspace, binds)
	output = base / 'singularity_synthetic.json'
	if output.exists() or output.is_symlink():
		raise StagingError('Synthetic result already exists')
	mapped_output = map_host_path(str(output), workspace, binds)
	argv = [
		'singularity', 'exec', '--containall', '--no-home',
		'--bind', workspace + ':' + container_workspace + ':rw',
		image, '/bin/sh', '-c', _SYNTHETIC_SH, 'caesar-synthetic',
		mapped['image.fits'], mapped['solutions.tbl'], mapped_output
	]
	return runner(argv, check=False).returncode


def main(argv=None):
	parser = argparse.ArgumentParser(description='Fixed synthetic Singularity staging test')
	parser.add_argument('--workspace', required=True)
	parser.add_argument('--image', required=True)
	parser.add_argument('--container-workspace', required=True)
	args = parser.parse_args(argv)
	try:
		return execute(args.workspace, args.image, args.container_workspace)
	except (ValueError, OSError, StagingError, subprocess.SubprocessError) as exc:
		print('SINGULARITY_SYNTHETIC_FAILED: %s' % exc, file=sys.stderr)
		return 1


if __name__ == '__main__':
	sys.exit(main())
