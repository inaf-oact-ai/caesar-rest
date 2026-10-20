import hashlib
import json
from pathlib import Path

import pytest
from caesar_pipeline_runtime.integrity import validate_expected, verify_copy


def sha(data):
	return hashlib.sha256(data).hexdigest()


def test_file_copy_digest(tmp_path):
	p = tmp_path / 'input.dat'
	p.write_bytes(b'abc')
	contract = {'kind': 'file', 'sha256': sha(b'abc')}
	assert verify_copy(p, contract)
	p.write_bytes(b'xyz')  # same size, different contents
	with pytest.raises(ValueError):
		verify_copy(p, contract)


def test_directory_exact_structure_and_bytes(tmp_path):
	p = tmp_path / 'measurement.ms'
	p.mkdir()
	(p / 'table.dat').write_bytes(b'123')
	(p / 'SUBTABLE').mkdir()
	(p / 'SUBTABLE' / 'data').write_bytes(b'123')
	contract = {'kind': 'directory', 'manifest_entries': [
		{'path': 'SUBTABLE/', 'kind': 'directory'},
		{'path': 'SUBTABLE/data', 'kind': 'file', 'size_bytes': 3, 'sha256': sha(b'123')},
		{'path': 'table.dat', 'kind': 'file', 'size_bytes': 3, 'sha256': sha(b'123')}
	]}
	assert verify_copy(p, contract)
	(p / 'SUBTABLE' / 'data').write_bytes(b'xyz')
	with pytest.raises(ValueError):
		verify_copy(p, contract)
	(p / 'SUBTABLE' / 'data').write_bytes(b'123')
	(p / 'EXTRA').write_bytes(b'')
	with pytest.raises(ValueError):
		verify_copy(p, contract)


def test_symlink_not_allowed(tmp_path):
	p = tmp_path / 'ms'
	p.mkdir()
	(p / 'link').symlink_to('/etc/passwd')
	with pytest.raises(ValueError):
		verify_copy(p, {'kind': 'directory', 'manifest_entries': []})


def test_manifest_rejects_traversal():
	with pytest.raises(ValueError):
		validate_expected({'manifest_entries': [{'path': '../evil', 'kind': 'directory'}]}, 'directory')
