"""H2C2a: version-2 multi-input submission contract (not an executor).

Only trusted server-side code may supply ``sources`` and ``workspace_cluster``.
Never accept these paths directly from a REST payload. The v1 submission
adapter and worker remain unchanged until H2C2b.
"""
import os
import re

from pipeline_runtime.integrity import validate_expected


class MultiInputSpecError(ValueError):
	pass


_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
_OPTION = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')


def _path(value):
	if not isinstance(value, str) or not value.startswith('/') or '\x00' in value or '\n' in value or '\r' in value:
		raise MultiInputSpecError('Invalid absolute path')
	if os.path.normpath(value) != value or '//' in value:
		raise MultiInputSpecError('Noncanonical absolute path')
	return value


def _within(path, root):
	return path == root or path.startswith(root.rstrip('/') + '/')


def build_multi_input_specs(workspace_cluster, sources, image, arguments,
		input_options, execution_dir='execution', output_dir='results'):
	"""Build a v2 contract from server-verified source paths.

	``sources`` is a list of {input_name, source, kind, size_bytes} records,
	constructed from frozen artifact bindings, never from client paths.
	``input_options`` maps CLI option names to input names; each named input
	must be explicitly mapped exactly once. No --key=value rewriting occurs.
	"""
	workspace_cluster = _path(workspace_cluster)
	image = _path(image)
	if not isinstance(sources, list) or not 1 <= len(sources) <= 32:
		raise MultiInputSpecError('Expected 1-32 sources')
	if not isinstance(arguments, (list, tuple)) or not arguments:
		raise MultiInputSpecError('Invalid execution arguments')
	if not isinstance(input_options, dict) or not input_options:
		raise MultiInputSpecError('Missing input option mapping')
	if execution_dir != 'execution' or output_dir != 'results':
		raise MultiInputSpecError('Unsupported execution layout')
	
	seen = set()
	staging_inputs = []
	for item in sources:
		if not isinstance(item, dict):
			raise MultiInputSpecError('Invalid trusted input descriptor')

		# - Authorized read-only dataset reference.
		# - No size/hash contract: the source is not copied.
		if set(item) == {'input_name', 'source', 'mode'}:
			if item['mode'] != 'reference_ro':
				raise MultiInputSpecError('Invalid reference mode')

			name = item['input_name']
			if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen:
				raise MultiInputSpecError('Duplicate or invalid input name')

			source = _path(item['source'])
			if (
				source == workspace_cluster
				or _within(source, workspace_cluster)
				or _within(workspace_cluster, source)
			):
				raise MultiInputSpecError('Reference overlaps workspace')

			seen.add(name)
			staging_inputs.append({
				'name': name,
				'source': source,
				'mode': 'reference_ro',
				'writable': False
			})
			continue

		# - Existing integrity-verified private-copy input.
		if set(item) not in (
			{'input_name', 'source', 'kind', 'size_bytes', 'sha256'},
			{'input_name', 'source', 'kind', 'size_bytes', 'manifest_entries'}
		):
			raise MultiInputSpecError('Invalid trusted input descriptor')

		name, source, kind, size = (
			item[x]
			for x in ('input_name', 'source', 'kind', 'size_bytes')
		)

		if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen:
			raise MultiInputSpecError('Duplicate or invalid input name')

		seen.add(name)
		source = _path(source)

		if (
			source == workspace_cluster
			or _within(source, workspace_cluster)
			or _within(workspace_cluster, source)
		):
			raise MultiInputSpecError('Input source overlaps workspace')

		if kind not in ('file', 'directory') or type(size) is not int or size < 0:
			raise MultiInputSpecError('Invalid input type or size')

		try:
			validate_expected(item, kind)
		except ValueError as exc:
			raise MultiInputSpecError('Invalid expected integrity data') from exc

		descriptor = {
			'name': name,
			'source': source,
			'kind': kind,
			'size_bytes': size,
			'mode': 'copy',
			'writable': True
		}

		if kind == 'file':
			descriptor['sha256'] = item['sha256']
		else:
			descriptor['manifest_entries'] = item['manifest_entries']

		staging_inputs.append(descriptor)	
	
			
	options = {}
	for option, name in input_options.items():
		if not isinstance(option, str) or not _OPTION.fullmatch(option) or name not in seen:
			raise MultiInputSpecError('Invalid input option mapping')
		if name in options.values():
			raise MultiInputSpecError('An input cannot map to multiple options')
		options[option] = name
	if set(options.values()) != seen:
		raise MultiInputSpecError('Every input must have an explicit option')
	clean_args = []
	for arg in arguments:
		if (not isinstance(arg, str) or not arg.startswith('--') or
				any(c.isspace() or c in "'\"\\$`\x00" for c in arg)):
			raise MultiInputSpecError('Invalid execution argument')
		if any(arg == '--' + option or arg.startswith('--' + option + '=') for option in options):
			raise MultiInputSpecError('Input option duplicated in arguments')
		clean_args.append(arg)
	staging = {'version': 2, 'inputs': staging_inputs}
	execution = {'version': 2, 'image': image, 'container_workspace': workspace_cluster,
		'arguments': clean_args, 'input_options': options,
		'execution_dir': execution_dir, 'output_dir': output_dir, 'environment': {}}
	return staging, execution


def validate_multi_input_pair(staging, execution):
	"""Validate a v2 pair for contract-level tests; does not stage or execute."""
	if not isinstance(staging, dict) or not isinstance(execution, dict):
		raise MultiInputSpecError('Invalid specs')
		
	if set(staging) != {'version', 'inputs'} or staging['version'] != 2:
		raise MultiInputSpecError('Not a v2 staging specification')
	
	if (set(execution) != {'version', 'image', 'container_workspace', 'arguments',
			'input_options', 'execution_dir', 'output_dir', 'environment'} or
			execution['version'] != 2 or execution['environment'] != {}):
		raise MultiInputSpecError('Not a supported v2 execution specification')
	
	fresh = build_multi_input_specs(
		execution['container_workspace'],
		[
			(
				{
					'input_name': item.get('name'),
					'source': item.get('source'),
					'mode': 'reference_ro'
				}
				if item.get('mode') == 'reference_ro'
				else {
					'input_name': item.get('name'),
					'source': item.get('source'),
					'kind': item.get('kind'),
					'size_bytes': item.get('size_bytes'),
					**(
						{'sha256': item['sha256']}
						if 'sha256' in item
						else {'manifest_entries': item.get('manifest_entries')}
					)
				}
			)
			for item in staging['inputs']
		],
		execution['image'],
		execution['arguments'],
		execution['input_options'],
		execution['execution_dir'],
		execution['output_dir']
	)
	
	if fresh != (staging, execution):
		raise MultiInputSpecError('Unexpected or noncanonical v2 specification')
	
	return True
