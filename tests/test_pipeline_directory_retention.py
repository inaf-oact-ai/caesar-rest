import hashlib

import pytest

from caesar_rest.pipeline.artifacts.directory_retention import DirectoryRetentionError, copy_directory_artifact


def build_source(tmp_path):
	source = tmp_path / 'source.ms'
	source.mkdir()
	(source / 'table.dat').write_bytes(b'hello')
	(source / 'SUBTABLE').mkdir()
	(source / 'SUBTABLE' / 'info').write_bytes(b'world')
	(source / 'EMPTY').mkdir()
	return source


def metadata():
	return {'size_bytes': 10, 'file_count': 2, 'directory_count': 2}


def test_copy_preserves_tree_and_manifest(tmp_path):
	source = build_source(tmp_path)
	target = tmp_path / 'retained.ms'
	result = copy_directory_artifact(str(source), str(target), metadata())
	assert (target / 'table.dat').read_bytes() == b'hello'
	assert (target / 'SUBTABLE' / 'info').read_bytes() == b'world'
	assert (target / 'EMPTY').is_dir()
	assert result['manifest']['file_count'] == 2
	assert result['manifest']['entries'][0]['kind'] == 'directory'
	assert any(x.get('sha256') == hashlib.sha256(b'hello').hexdigest()
		for x in result['manifest']['entries'])


def test_refuse_symlink_and_leave_no_destination(tmp_path):
	source = build_source(tmp_path)
	(source / 'link').symlink_to(source / 'table.dat')
	target = tmp_path / 'retained.ms'
	with pytest.raises(DirectoryRetentionError):
		copy_directory_artifact(str(source), str(target), metadata())
	assert not target.exists()


def test_refuse_changed_discovery(tmp_path):
	source = build_source(tmp_path)
	target = tmp_path / 'retained.ms'

	with pytest.raises(
		DirectoryRetentionError,
		match='Directory metadata mismatch:.*field=size_bytes'
	):
		copy_directory_artifact(
			str(source),
			str(target),
			{'size_bytes': 9, 'file_count': 2, 'directory_count': 2}
		)

	assert not target.exists()


def test_refuse_excessive_bytes(tmp_path):
	source = build_source(tmp_path)
	with pytest.raises(DirectoryRetentionError, match='size limit'):
		copy_directory_artifact(str(source), str(tmp_path / 'retained.ms'), metadata(), max_bytes=9)


def test_no_overwrite(tmp_path):
	source = build_source(tmp_path)
	target = tmp_path / 'retained.ms'
	target.mkdir()
	with pytest.raises(DirectoryRetentionError, match='already exists'):
		copy_directory_artifact(str(source), str(target), metadata())


def test_reject_special_file(tmp_path):
	import os
	source = build_source(tmp_path)
	os.mkfifo(str(source / 'pipe'))
	with pytest.raises(DirectoryRetentionError):
		copy_directory_artifact(str(source), str(tmp_path / 'retained.ms'), metadata())
