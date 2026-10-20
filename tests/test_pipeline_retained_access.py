import hashlib

import pytest

from caesar_rest.pipeline.artifacts import access
from caesar_rest.pipeline.artifacts import retention
from caesar_rest.pipeline import manager


def make_retained_run(tmp_path, content=b'{"ok":true}'):
	root = tmp_path / 'artifacts'
	directory = root / 'tester' / 'pipeline1' / 'run1'
	directory.mkdir(parents=True)

	(directory / '0000').write_bytes(content)

	run = {
		'pipeline_id': 'pipeline1',
		'run_id': 'run1',
		'status': 'COMPLETED',
		'artifacts': [{
			'name': 'project_info',
			'relative_path': 'results/project_info.json',
			'type': 'application/json',
			'size_bytes': len(content)
		}],
		'retained_artifacts': [{
			'index': 0,
			'size_bytes': len(content),
			'sha256': hashlib.sha256(content).hexdigest()
		}]
	}

	return str(root), directory, run


def test_retained_artifact_opens_without_job_workspace(tmp_path):
	root, _, run = make_retained_run(tmp_path)

	fileobj, filename, mime = access.open_registered_artifact(
		None, 'tester', run, 0, retention_root=root
	)

	with fileobj:
		assert fileobj.read() == b'{"ok":true}'

	assert filename == 'project_info.json'
	assert mime == 'application/json'


def test_retained_artifact_checksum_mismatch(tmp_path):
	root, directory, run = make_retained_run(tmp_path)

	# Same size, different content.
	(directory / '0000').write_bytes(b'{"ok":xxxx}')

	with pytest.raises(manager.PipelineError) as exc:
		access.open_registered_artifact(
			None, 'tester', run, 0, retention_root=root
		)

	assert exc.value.status == 409


def test_missing_retained_artifact_does_not_fallback(tmp_path):
	root, directory, run = make_retained_run(tmp_path)
	(directory / '0000').unlink()

	with pytest.raises(manager.PipelineError) as exc:
		access.open_registered_artifact(
			None, 'tester', run, 0, retention_root=root
		)

	assert exc.value.status == 410


def test_retained_artifact_rejects_symlink(tmp_path):
	root, directory, run = make_retained_run(tmp_path)
	target = directory / 'original'
	target.write_bytes(b'{"ok":true}')

	(directory / '0000').unlink()
	(directory / '0000').symlink_to(target)

	with pytest.raises(manager.PipelineError):
		access.open_registered_artifact(
			None, 'tester', run, 0, retention_root=root
		)
