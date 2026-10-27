"""Regression tests for lightweight V2 artifact verification and staging integrity.

Place under tests/test_pipeline_lightweight_manifest.py.
"""
import hashlib
import json

import pytest

from caesar_rest.pipeline.artifacts.directory_integrity import (
	DirectoryIntegrityError,
	verify_directory_manifest,
)
from pipeline_runtime.staging import StagingError, stage_inputs


def make_retained(tmp_path, payload=b'original-data'):
	base = tmp_path / 'retained'
	base.mkdir()
	artifact = base / '0000'
	artifact.mkdir()
	(artifact / 'DATA').write_bytes(payload)
	entries = [
		{'path': 'DATA', 'kind': 'file', 'size_bytes': len(payload),
			'sha256': hashlib.sha256(payload).hexdigest()}
	]
	manifest = {
		'version': 1, 'kind': 'directory', 'size_bytes': len(payload),
		'file_count': 1, 'directory_count': 0, 'entries': entries
	}
	data = json.dumps(manifest, sort_keys=True, separators=(',', ':'),
		ensure_ascii=False).encode('utf-8')
	(base / '0000.manifest.json').write_bytes(data)
	record = {
		'index': 0, 'kind': 'directory', 'size_bytes': len(payload),
		'file_count': 1, 'directory_count': 0,
		'manifest_name': '0000.manifest.json',
		'manifest_sha256': hashlib.sha256(data).hexdigest(),
	}
	return base, artifact, record, entries


def test_valid_manifest_is_accepted(tmp_path):
	base, _, record, _ = make_retained(tmp_path)
	result = verify_directory_manifest(str(base), 0, record)
	assert result['verified'] is True
	assert result['size_bytes'] == record['size_bytes']


def test_sidecar_tampering_is_rejected(tmp_path):
	base, _, record, _ = make_retained(tmp_path)
	with (base / '0000.manifest.json').open('ab') as output:
		output.write(b' ')
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_manifest(str(base), 0, record)


def test_wrong_record_digest_is_rejected(tmp_path):
	base, _, record, _ = make_retained(tmp_path)
	record['manifest_sha256'] = '0' * 64
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_manifest(str(base), 0, record)


def test_missing_artifact_directory_is_rejected(tmp_path):
	base, artifact, record, _ = make_retained(tmp_path)
	(artifact / 'DATA').unlink()
	artifact.rmdir()
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_manifest(str(base), 0, record)


def test_symlinked_artifact_root_is_rejected(tmp_path):
	base, artifact, record, _ = make_retained(tmp_path)
	other = tmp_path / 'other'
	artifact.rename(other)
	artifact.symlink_to(other, target_is_directory=True)
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_manifest(str(base), 0, record)


def test_inconsistent_metadata_is_rejected(tmp_path):
	base, _, record, _ = make_retained(tmp_path)
	record['file_count'] = 2
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_manifest(str(base), 0, record)


def test_same_size_source_corruption_is_deferred_and_worker_rejects(tmp_path):
	base, artifact, record, entries = make_retained(tmp_path)
	(artifact / 'DATA').write_bytes(b'altered!-data')
	assert len((artifact / 'DATA').read_bytes()) == record['size_bytes']

	# Lightweight API check intentionally does not read file contents.
	assert verify_directory_manifest(str(base), 0, record)['verified']

	workspace = tmp_path / 'job'
	workspace.mkdir()
	with pytest.raises(StagingError):
		stage_inputs([{
			'source': str(artifact), 'name': 'target_ms', 'mode': 'copy',
			'writable': True, 'kind': 'directory',
			'size_bytes': record['size_bytes'],
			'manifest_entries': entries,
		}], str(workspace))
	assert not (workspace / 'input' / 'staging.json').exists()


def test_extra_source_file_is_rejected_before_ready(tmp_path):
	base, artifact, record, entries = make_retained(tmp_path)
	(artifact / 'EXTRA').write_bytes(b'')
	assert verify_directory_manifest(str(base), 0, record)['verified']
	workspace = tmp_path / 'job'
	workspace.mkdir()
	with pytest.raises(StagingError):
		stage_inputs([{
			'source': str(artifact), 'name': 'target_ms', 'mode': 'copy',
			'writable': True, 'kind': 'directory',
			'size_bytes': record['size_bytes'],
			'manifest_entries': entries,
		}], str(workspace))
	assert not (workspace / 'input' / 'staging.json').exists()
