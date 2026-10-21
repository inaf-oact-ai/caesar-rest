
import json
import os

import pytest

from pipeline_runtime.staging import (
	StagingError,
	stage_inputs,
)


def test_reference_does_not_copy_dataset(tmp_path):
	source = tmp_path / 'observation.ms'
	source.mkdir()

	(source / 'table.dat').write_bytes(b'synthetic-ms-data')

	workspace = tmp_path / 'job'
	workspace.mkdir()

	manifest = stage_inputs(
		[{
			'source': str(source),
			'name': 'observation.ms',
			'mode': 'reference_ro',
			'writable': False
		}],
		str(workspace)
	)

	entry = manifest['inputs'][0]

	assert manifest['staging_state'] == 'READY'
	assert entry['strategy'] == 'read_only_reference'
	assert entry['input_isolation'] == 'shared_read_only'
	assert entry['writable'] is False
	assert entry['source_dev'] == source.stat().st_dev
	assert entry['source_ino'] == source.stat().st_ino

	# The private destination is an empty placeholder.
	destination = workspace / 'input' / 'observation.ms'

	assert destination.is_dir()
	assert list(destination.iterdir()) == []

	# Original source has not been modified.
	assert (source / 'table.dat').read_bytes() == (
		b'synthetic-ms-data'
	)

	assert (
		workspace / 'input' / 'staging.json'
	).is_file()


def test_reference_rejects_writable_mode(tmp_path):
	source = tmp_path / 'observation.ms'
	source.mkdir()

	workspace = tmp_path / 'job'
	workspace.mkdir()

	with pytest.raises(StagingError):
		stage_inputs(
			[{
				'source': str(source),
				'name': 'observation.ms',
				'mode': 'reference_ro',
				'writable': True
			}],
			str(workspace)
		)

	assert not (workspace / 'input').exists()


def test_reference_rejects_symlinked_source(tmp_path):
	actual = tmp_path / 'actual.ms'
	actual.mkdir()

	link = tmp_path / 'linked.ms'
	link.symlink_to(actual, target_is_directory=True)

	workspace = tmp_path / 'job'
	workspace.mkdir()

	with pytest.raises(StagingError):
		stage_inputs(
			[{
				'source': str(link),
				'name': 'linked.ms',
				'mode': 'reference_ro',
				'writable': False
			}],
			str(workspace)
		)

	assert not (workspace / 'input').exists()


def test_reference_rejects_nested_symlinks(tmp_path):
	source = tmp_path / 'observation.ms'
	source.mkdir()

	external = tmp_path / 'external'
	external.mkdir()

	(source / 'linked').symlink_to(
		external,
		target_is_directory=True
	)

	workspace = tmp_path / 'job'
	workspace.mkdir()

	with pytest.raises(StagingError):
		stage_inputs(
			[{
				'source': str(source),
				'name': 'observation.ms',
				'mode': 'reference_ro',
				'writable': False
			}],
			str(workspace)
		)


def test_copy_mode_still_works(tmp_path):
	source = tmp_path / 'sample.dat'
	source.write_bytes(b'example')

	workspace = tmp_path / 'job'
	workspace.mkdir()

	manifest = stage_inputs(
		[{
			'source': str(source),
			'name': 'sample.dat',
			'mode': 'copy',
			'writable': True
		}],
		str(workspace)
	)

	entry = manifest['inputs'][0]

	assert entry['strategy'] == 'full_copy'
	assert entry['input_isolation'] == 'private_copy'

	assert (
		workspace / 'input' / 'sample.dat'
	).read_bytes() == b'example'



from types import SimpleNamespace

from pipeline_runtime.resolver import resolve_staged_inputs
from pipeline_runtime.executor import execute


def make_reference_workspace(tmp_path):
	source = tmp_path / 'observation.ms'
	source.mkdir()
	(source / 'table.dat').write_bytes(b'synthetic-ms-data')

	workspace = tmp_path / 'job'
	workspace.mkdir()

	staging_spec = {
		'version': 1,
		'inputs': [{
			'source': str(source),
			'name': 'observation.ms',
			'mode': 'reference_ro',
			'writable': False,
		}]
	}

	(workspace / 'staging_spec.json').write_text(
		json.dumps(staging_spec)
	)

	stage_inputs(staging_spec['inputs'], str(workspace))

	return source, workspace


def test_reference_resolves_without_copy(tmp_path):
	source, workspace = make_reference_workspace(tmp_path)

	paths, references = resolve_staged_inputs(
		str(workspace),
		include_references=True
	)

	assert paths['observation.ms'] == str(
		workspace / 'input' / 'observation.ms'
	)

	assert references['observation.ms']['source'] == str(source)

	assert not (
		workspace / 'input' / 'observation.ms' / 'table.dat'
	).exists()


def test_reference_default_resolver_return_unchanged(tmp_path):
	source, workspace = make_reference_workspace(tmp_path)

	paths = resolve_staged_inputs(str(workspace))

	assert isinstance(paths, dict)
	assert 'observation.ms' in paths


def test_reference_rejects_source_tampering(tmp_path):
	source, workspace = make_reference_workspace(tmp_path)

	other = tmp_path / 'other.ms'
	other.mkdir()

	manifest_path = workspace / 'input' / 'staging.json'
	manifest = json.loads(manifest_path.read_text())

	manifest['inputs'][0]['source'] = str(other)

	manifest_path.write_text(json.dumps(manifest))

	with pytest.raises(StagingError):
		resolve_staged_inputs(
			str(workspace),
			include_references=True
		)


def test_reference_rejects_identity_change(tmp_path):
	source, workspace = make_reference_workspace(tmp_path)

	manifest_path = workspace / 'input' / 'staging.json'
	manifest = json.loads(manifest_path.read_text())

	manifest['inputs'][0]['source_ino'] = -1
	manifest_path.write_text(json.dumps(manifest))

	with pytest.raises(StagingError):
		resolve_staged_inputs(
			str(workspace),
			include_references=True
		)


def test_reference_rejects_nonempty_mount_point(tmp_path):
	source, workspace = make_reference_workspace(tmp_path)

	mount_point = workspace / 'input' / 'observation.ms'
	(mount_point / 'unexpected.txt').write_text('unexpected')

	with pytest.raises(StagingError):
		resolve_staged_inputs(
			str(workspace),
			include_references=True
		)


def test_reference_executor_builds_read_only_bind(tmp_path):
	source, workspace = make_reference_workspace(tmp_path)

	image = tmp_path / 'test.sif'
	image.write_bytes(b'synthetic-image-placeholder')

	execution_spec = {
		'version': 1,
		'image': str(image),
		'container_workspace': '/job-workspace',
		'arguments': ['--stage=GET_INFO'],
		'input_options': {
			'input-ms': 'observation.ms'
		},
		'execution_dir': 'execution',
		'output_dir': 'results',
		'environment': {}
	}

	spec_path = workspace / 'execution_spec.json'
	spec_path.write_text(json.dumps(execution_spec))

	commands = []

	def fake_runner(cmd, check=False):
		commands.append(cmd)
		return SimpleNamespace(returncode=0)

	assert execute(
		str(workspace),
		str(spec_path),
		runner=fake_runner
	) == 0

	assert len(commands) == 1

	cmd = commands[0]

	assert (
		str(source) +
		':/job-workspace/input/observation.ms:ro'
	) in cmd

	assert (
		str(workspace) +
		':/job-workspace:rw'
	) in cmd

	assert (
		str(source) +
		':/job-workspace/input/observation.ms:rw'
	) not in cmd

	assert (
		'JOB_OPTIONS=--stage=GET_INFO '
		'--input-ms=/job-workspace/input/observation.ms'
	) in cmd

	assert not (
		workspace / 'input' / 'observation.ms' / 'table.dat'
	).exists()


def test_copy_resolver_backward_compatibility(tmp_path):
	source = tmp_path / 'sample.dat'
	source.write_bytes(b'example')

	workspace = tmp_path / 'job'
	workspace.mkdir()

	stage_inputs(
		[{
			'source': str(source),
			'name': 'sample.dat',
			'mode': 'copy',
			'writable': True
		}],
		str(workspace)
	)

	# Existing callers receive a dictionary.
	paths = resolve_staged_inputs(str(workspace))

	assert isinstance(paths, dict)
	assert 'sample.dat' in paths

	# New callers explicitly request reference metadata.
	paths, references = resolve_staged_inputs(
		str(workspace),
		include_references=True
	)

	assert isinstance(paths, dict)
	assert references == {}

