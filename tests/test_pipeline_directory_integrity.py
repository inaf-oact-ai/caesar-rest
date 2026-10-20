import hashlib
import json

import pytest

from caesar_rest.pipeline_directory_retention import DirectoryRetentionError, copy_directory_artifact
from caesar_rest.pipeline_directory_integrity import DirectoryIntegrityError, verify_directory_artifact


def build(tmp_path):
	source = tmp_path / 'source.ms'
	source.mkdir()
	(source / 'table.dat').write_bytes(b'hello')
	(source / 'EMPTY').mkdir()
	(source / 'ANTENNA').mkdir()
	(source / 'ANTENNA' / 'data').write_bytes(b'world')
	base = tmp_path / 'retained'
	base.mkdir()
	result = copy_directory_artifact(str(source), str(base / '0000'),
		{'size_bytes': 10, 'file_count': 2, 'directory_count': 2})
	payload = json.dumps(result['manifest'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
	(base / '0000.manifest.json').write_bytes(payload)
	record = {'index': 0, 'kind': 'directory', 'manifest_name': '0000.manifest.json',
		'manifest_sha256': hashlib.sha256(payload).hexdigest(), 'size_bytes': 10,
		'file_count': 2, 'directory_count': 2}
	return base, record


def test_valid_directory(tmp_path):
	base, record = build(tmp_path)
	assert verify_directory_artifact(str(base), 0, record)['verified']


def test_modified_same_size_detected(tmp_path):
	base, record = build(tmp_path)
	(base / '0000' / 'table.dat').write_bytes(b'HELLO')
	with pytest.raises(DirectoryIntegrityError, match='mismatch'):
		verify_directory_artifact(str(base), 0, record)


def test_extra_and_missing_files_detected(tmp_path):
	base, record = build(tmp_path)
	(base / '0000' / 'extra').write_bytes(b'x')
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_artifact(str(base), 0, record)
	(base / '0000' / 'extra').unlink()
	(base / '0000' / 'table.dat').unlink()
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_artifact(str(base), 0, record)


def test_corrupt_manifest_detected(tmp_path):
	base, record = build(tmp_path)
	(base / '0000.manifest.json').write_bytes(b'{}')
	with pytest.raises(DirectoryIntegrityError, match='checksum'):
		verify_directory_artifact(str(base), 0, record)


def test_symlink_detected(tmp_path):
	base, record = build(tmp_path)
	(base / '0000' / 'table.dat').unlink()
	(base / '0000' / 'table.dat').symlink_to(base / '0000' / 'ANTENNA' / 'data')
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_artifact(str(base), 0, record)


def test_does_not_replace_existing_target(tmp_path):
	base, _ = build(tmp_path)
	new_source = tmp_path / 'replacement.ms'
	new_source.mkdir()
	(new_source / 'table.dat').write_bytes(b'other')
	with pytest.raises(DirectoryRetentionError, match='already exists'):
		copy_directory_artifact(str(new_source), str(base / '0000'),
			{'size_bytes': 5, 'file_count': 1, 'directory_count': 0})
	assert (base / '0000' / 'table.dat').read_bytes() == b'hello'


def test_rejects_manifest_directory_symlink(tmp_path):
	base, record = build(tmp_path)
	(base / '0000' / 'ANTENNA' / 'data').unlink()
	(base / '0000' / 'ANTENNA').rmdir()
	(base / '0000' / 'ANTENNA').symlink_to(base / '0000' / 'EMPTY')
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_artifact(str(base), 0, record)
