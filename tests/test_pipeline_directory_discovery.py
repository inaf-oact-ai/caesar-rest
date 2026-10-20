"""H2D-C1 directory metadata discovery tests; no retention or Slurm."""

import pytest

from caesar_rest.pipeline.artifacts.discovery import ArtifactDiscoveryError, discover_artifacts


def contract(**kwargs):
	return {'ms': dict({'path': 'calibrated.ms', 'kind': 'directory', 'required': True}, **kwargs)}


def workspace(tmp_path):
	results = tmp_path / 'results'
	results.mkdir()
	ms = results / 'calibrated.ms'
	ms.mkdir()
	return ms


def test_directory_metadata(tmp_path):
	ms = workspace(tmp_path)
	(ms / 'table.dat').write_bytes(b'1234')
	(ms / 'subtables').mkdir()
	(ms / 'subtables' / 'ANTENNA').write_bytes(b'abc')
	items = discover_artifacts(str(tmp_path), contract())
	assert items == [{
		'name': 'ms', 'relative_path': 'results/calibrated.ms',
		'type': 'application/octet-stream', 'role': 'output',
		'kind': 'directory', 'size_bytes': 7,
		'file_count': 2, 'directory_count': 1
	}]


def test_directory_symlink_rejected(tmp_path):
	ms = workspace(tmp_path)
	outside = tmp_path / 'outside'
	outside.write_bytes(b'x')
	(ms / 'link').symlink_to(outside)
	with pytest.raises(ArtifactDiscoveryError, match='Symlink'):
		discover_artifacts(str(tmp_path), contract())


def test_directory_limits(tmp_path):
	ms = workspace(tmp_path)
	(ms / 'a').write_bytes(b'123')
	(ms / 'b').write_bytes(b'456')
	with pytest.raises(ArtifactDiscoveryError, match='entry limit'):
		discover_artifacts(str(tmp_path), contract(), max_directory_entries=1)
	with pytest.raises(ArtifactDiscoveryError, match='size limit'):
		discover_artifacts(str(tmp_path), contract(), max_directory_bytes=5)


def test_directory_depth_and_special_file(tmp_path):
	ms = workspace(tmp_path)
	(ms / 'one').mkdir()
	(ms / 'one' / 'two').mkdir()
	with pytest.raises(ArtifactDiscoveryError, match='depth limit'):
		discover_artifacts(str(tmp_path), contract(), max_directory_depth=1)


def test_existing_file_contract_unchanged(tmp_path):
	ms = workspace(tmp_path)
	(ms.parent / 'manifest.json').write_bytes(b'{}')
	items = discover_artifacts(str(tmp_path), {
		'manifest': {'path': 'manifest.json', 'required': True}
	})
	assert items == [{
		'name': 'manifest', 'relative_path': 'results/manifest.json',
		'type': 'application/octet-stream', 'role': 'output',
		'size_bytes': 2
	}]


def test_directory_contract_does_not_accept_file(tmp_path):
	ms = workspace(tmp_path)
	(ms.parent / 'file.ms').write_bytes(b'a')
	with pytest.raises(ArtifactDiscoveryError, match='not a directory'):
		discover_artifacts(str(tmp_path), {'ms': {'path': 'file.ms', 'kind': 'directory'}})
