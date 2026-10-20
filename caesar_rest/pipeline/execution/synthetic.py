"""Synthetic host-side consumer for testing PREPARE -> RESOLVE -> EXECUTE.

This is NOT a general command runner. The fixture names and operation are fixed.
No REST request or staging specification may select a subprocess command.
"""
import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from caesar_pipeline_runtime.staging import StagingError
from caesar_pipeline_runtime.resolver import resolve_staged_inputs


def synthetic_execution_command(workspace, runner_path, python_executable='/usr/bin/python3'):
	"""Generate shell-safe invocation of the fixed synthetic consumer."""
	for name, value in (('workspace', workspace), ('runner_path', runner_path),
	                    ('python_executable', python_executable)):
		if not isinstance(value, str) or not os.path.isabs(value) or '\x00' in value or '\n' in value:
			raise ValueError('%s must be a clean absolute path' % name)
	return ' '.join(shlex.quote(v) for v in (
		python_executable, runner_path, '--workspace', workspace
	))


def consume(workspace):
	"""Read a staged file, modify only a staged directory, record test result."""
	paths = resolve_staged_inputs(workspace, required_names=['image.fits', 'solutions.tbl'])
	image = Path(paths['image.fits'])
	solutions = Path(paths['solutions.tbl'])
	if not image.is_file() or not solutions.is_dir():
		raise StagingError('Wrong synthetic input types')
	if image.read_bytes() != b'test fits\n':
		raise StagingError('Unexpected synthetic FITS fixture')
	data = solutions / 'data'
	if data.is_symlink() or not data.is_file() or data.read_bytes() != b'test table\n':
		raise StagingError('Unexpected synthetic table fixture')
	# Mutate only the private copy: read-only source must remain unchanged.
	data.write_bytes(b'synthetic execution changed private table\n')
	result_path = Path(workspace) / 'synthetic_execution.json'
	if result_path.exists() or result_path.is_symlink():
		raise StagingError('Synthetic output already exists; refusing overwrite')
	with result_path.open('x', encoding='utf-8') as fp:
		json.dump({'status': 'EXECUTED', 'inputs': ['image.fits', 'solutions.tbl']}, fp)
		fp.write('\n')
	return result_path


def main(argv=None):
	parser = argparse.ArgumentParser(description='Fixed synthetic staged-input consumer')
	parser.add_argument('--workspace', required=True)
	args = parser.parse_args(argv)
	try:
		result_path = consume(args.workspace)
	except (StagingError, OSError, ValueError) as exc:
		print('SYNTHETIC_EXECUTION_FAILED: %s' % exc, file=sys.stderr)
		return 1
	print('SYNTHETIC_EXECUTION_OK %s' % result_path)
	return 0


if __name__ == '__main__':
	sys.exit(main())
