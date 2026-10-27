"""Generic, trusted staged-input execution through a registered Singularity image.

The caller must authorize image, arguments and staging specification before
writing a job-local execution specification. Never expose these controls as
arbitrary REST client-provided commands or images.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from pipeline_runtime.paths import map_staged_inputs, map_host_path
from pipeline_runtime.resolver import resolve_staged_inputs
from pipeline_runtime.version import specification_version


class ContainerExecutionError(ValueError):
	pass


def _absolute(path, label):
	if not isinstance(path, str) or not path.startswith('/') or any(ch in path for ch in '\x00\r\n'):
		raise ContainerExecutionError('%s must be an absolute clean path' % label)
	if '//' in path or any(part in ('.', '..') for part in path.split('/')) or (len(path) > 1 and path.endswith('/')):
		raise ContainerExecutionError('%s must be normalized' % label)
	return path


def execution_command(workspace, spec_path, runner_path, python_executable='/usr/bin/python3'):
	"""Build shell-safe host-side command for the generic executor."""
	for label, val in (('workspace', workspace), ('spec_path', spec_path), ('runner_path', runner_path), ('python_executable', python_executable)):
		_absolute(val, label)
	if os.path.dirname(spec_path) != workspace:
		raise ContainerExecutionError('Execution spec must be in private job workspace')
	return shlex.join([python_executable, runner_path, '--workspace', workspace, '--spec', spec_path])


def _validated_spec(spec, workspace):
	
	version = specification_version(spec, ContainerExecutionError)

	required_fields = {
		'image',
		'container_workspace',
		'arguments',
		'input_options',
		'execution_dir',
		'output_dir'
	}

	if (
		not isinstance(spec, dict)
		or not required_fields.issubset(spec)
		or set(spec) - (required_fields | {'environment', 'version'})
	):
		raise ContainerExecutionError('Invalid trusted execution spec schema')

	if version == 2 and 'version' not in spec:
		raise ContainerExecutionError('v2 requires an explicit version')

	image = _absolute(spec['image'], 'image')
	container_ws = _absolute(spec['container_workspace'], 'container_workspace')
	if container_ws == '/':
		raise ContainerExecutionError('Container workspace cannot be root')
	
	if not isinstance(spec['arguments'], list) or not isinstance(spec['input_options'], dict):
		raise ContainerExecutionError('Invalid options')
	
	if not spec['arguments'] or len(spec['arguments']) > 128:
		raise ContainerExecutionError('Invalid argument count')
	
	for item in spec['arguments']:
		if not isinstance(item, str) or not item.startswith('--') or any(c.isspace() or c in "'\"\\$`\x00" for c in item):
			raise ContainerExecutionError('Invalid application argument')
			
	
	for option, name in spec['input_options'].items():
		if not isinstance(option, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*', option):
			raise ContainerExecutionError('Invalid input option name')

		if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
			raise ContainerExecutionError('Invalid input binding')

		if version == 2 and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', name):
			raise ContainerExecutionError('Invalid v2 input name')

	if version == 2 and (
		not 1 <= len(spec['input_options']) <= 32
		or len(set(spec['input_options'].values())) != len(spec['input_options'])
	):
		raise ContainerExecutionError('Invalid v2 input mapping')
	
	for field in ('execution_dir', 'output_dir'):
		val = spec[field]
		if not isinstance(val, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', val):
			raise ContainerExecutionError('Invalid workspace subdirectory')
	
	if spec['execution_dir'] == spec['output_dir'] or spec['execution_dir'] == 'input' or spec['output_dir'] == 'input':
		raise ContainerExecutionError('Execution/output directories must be distinct from staging')
	
	environment = spec.get('environment', {})
	if not isinstance(environment, dict) or set(environment) - {'MODEL_DIR', 'APP_MODE'}:
		raise ContainerExecutionError('Invalid application environment')
	
	for key, value in environment.items():
		if not isinstance(value, str) or any(ch in value for ch in '\x00\r\n'):
			raise ContainerExecutionError('Invalid application environment value')
		if key == 'MODEL_DIR':
			_absolute(value, 'MODEL_DIR')
		if key == 'APP_MODE' and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
			raise ContainerExecutionError('Invalid APP_MODE')

	return image, container_ws


def execute(workspace, spec_path, runner=subprocess.run):
	"""Consume validated READY inputs and invoke fixed Singularity runscript."""
	
	_absolute(workspace, 'workspace')
	_absolute(spec_path, 'spec_path')
	if os.path.dirname(spec_path) != workspace:
		raise ContainerExecutionError('Execution spec must be in workspace')
	
	base = Path(workspace)
	if not base.is_dir() or base.is_symlink() or str(base.resolve(strict=True)) != workspace:
		raise ContainerExecutionError('Invalid private workspace')
	
	sp = Path(spec_path)
	if sp.is_symlink() or not sp.is_file():
		raise ContainerExecutionError('Missing trusted execution spec')
	
	with sp.open(encoding='utf8') as f:
		spec = json.load(f)
	
	image, container_ws = _validated_spec(spec, workspace)
	if not Path(image).is_file() or Path(image).is_symlink():
		raise ContainerExecutionError('Trusted container image missing or symlinked')
	
	paths, references = resolve_staged_inputs(
		workspace,
		required_names=list(spec['input_options'].values())
		if spec['input_options'] else None,
		include_references=True
	)	
	
	if specification_version(spec, ContainerExecutionError) == 2:
		if set(paths) != set(spec['input_options'].values()):
			raise ContainerExecutionError(
				'v2 staged inputs do not match execution bindings'
			)

	binds = [{'source': workspace, 'destination': container_ws}]
	mapped = map_staged_inputs(paths, workspace, binds)
	

	# - Build explicit read-only mounts for referenced inputs.
	# - Destinations remain inside the writable private workspace,
	#   but the mounted source itself is read-only.
	reference_binds = []

	for name, reference in references.items():

		if name not in spec['input_options'].values():
			raise ContainerExecutionError(
				'Unbound reference input: %s' % name
			)

		mount_point = reference['mount_point']
		source = reference['source']

		container_mount = map_host_path(
			mount_point,
			workspace,
			binds
		)

		reference_binds.append(
			'%s:%s:ro' % (source, container_mount)
		)
	
	
	args = list(spec['arguments'])
	for opt, name in spec['input_options'].items():
		if any(arg.startswith('--' + opt + '=') for arg in args):
			raise ContainerExecutionError('Input option already present in application arguments')
		args.append('--%s=%s' % (opt, mapped[name]))
	options = ' '.join(args)
	exec_dir = base / spec['execution_dir']
	out_dir = base / spec['output_dir']
	for directory in (exec_dir, out_dir):
		if directory.exists() or directory.is_symlink():
			raise ContainerExecutionError('Execution/output directory already exists')
	# Create directories after all validations. Existing workspace is never reused.
	exec_dir.mkdir(mode=0o700)
	out_dir.mkdir(mode=0o700)
	c_exec = map_host_path(str(exec_dir), workspace, binds)
	c_out = map_host_path(str(out_dir), workspace, binds)
	cmd = [
		'singularity', 'run', '--containall', '--no-home',
		'--bind', workspace + ':' + container_ws + ':rw',
		'--env', 'CHANGE_RUNUSER=0',
		'--env', 'JOB_OPTIONS=' + options,
		'--env', 'JOB_DIR=' + c_exec,
		'--env', 'JOB_OUTDIR=' + c_out,
		image
	]
	for key, value in spec.get('environment', {}).items():
		cmd[-1:-1] = ['--env', key + '=' + value]

	# - Add reference mounts before the container image.
	# - A referenced dataset must not be mounted read/write.
	for reference_bind in reference_binds:
		cmd[-1:-1] = [
			'--bind',
			reference_bind
		]


	return runner(cmd, check=False).returncode


def main(argv=None):
	p = argparse.ArgumentParser(description=__doc__)
	p.add_argument('--workspace', required=True)
	p.add_argument('--spec', required=True)
	a = p.parse_args(argv)
	try:
		status = execute(a.workspace, a.spec)
		if status:
			print('CONTAINER_EXECUTION_FAILED: exit %d' % status, file=sys.stderr)
		else:
			print('CONTAINER_EXECUTION_OK')
		return status
	except (ValueError, OSError, json.JSONDecodeError) as exc:
		print('CONTAINER_EXECUTION_FAILED: %s' % exc, file=sys.stderr)
		return 1


if __name__ == '__main__':
	sys.exit(main())
