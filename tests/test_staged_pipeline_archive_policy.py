
"""Generic staged archive contract regression tests."""

import json
import tarfile

import pytest

from caesar_rest.pipeline.archive import ArchivePolicyError, make_diagnostic_archive


def make_workspace(tmp_path):
	root = tmp_path / 'job_123'
	(root / 'input').mkdir(parents=True)
	(root / 'results' / 'IMAGES').mkdir(parents=True)
	(root / 'results' / 'previews' / 'all').mkdir(parents=True)
	(root / 'results' / 'previews' / 'selected').mkdir(parents=True)
	(root / 'results' / 'previews' / 'catalog').mkdir(parents=True)
	(root / 'input' / 'staging.json').write_text('{"state":"READY"}')
	(root / 'input' / 'private.ms').write_bytes(b'secret')
	(root / 'results' / 'IMAGES' / 'image.fits').write_bytes(b'x' * 4096)
	(root / 'results' / 'previews' / 'all' / 'unused.png').write_bytes(b'png')
	(root / 'results' / 'previews' / 'selected' / 'preview_a.png').write_bytes(b'png')
	(root / 'results' / 'previews' / 'catalog' / 'sources.dat').write_text('sources')
	(root / 'results' / 'run.log').write_text('complete')
	return root


def test_explicit_policy_contains_only_selected_files(tmp_path):
	root = make_workspace(tmp_path)
	archive = tmp_path / 'job.tar.gz'
	make_diagnostic_archive(str(archive), str(root), {'include': [
		'results/*.log',
		'results/previews/selected/*.png',
		'results/previews/catalog/*.dat',
	]})
	with tarfile.open(archive, 'r:gz') as tar:
		names = set(tar.getnames())
		prefix = root.name + '/'
		assert prefix + 'input/staging.json' in names
		assert prefix + 'results/run.log' in names
		assert prefix + 'results/previews/selected/preview_a.png' in names
		assert prefix + 'results/previews/catalog/sources.dat' in names
		assert prefix + 'results/IMAGES/image.fits' not in names
		assert prefix + 'results/previews/all/unused.png' not in names
		assert prefix + 'input/private.ms' not in names
		manifest = json.load(tar.extractfile(prefix + 'archive_policy.json'))
		assert manifest['complete_scientific_output'] is False


@pytest.mark.parametrize('pattern', [
	'/etc/passwd', '../outside', 'results/../input/private.ms',
	'results/**/any', 'results/*/any.log', 'input/staging.json',
])
def test_reject_unsafe_patterns(tmp_path, pattern):
	root = make_workspace(tmp_path)
	with pytest.raises(ArchivePolicyError):
		make_diagnostic_archive(str(tmp_path / 'out.tar.gz'), str(root), {'include': [pattern]})


def test_reject_symlinked_selected_file(tmp_path):
	root = make_workspace(tmp_path)
	(root / 'results' / 'leak.log').symlink_to(root / 'input' / 'private.ms')
	with pytest.raises(ArchivePolicyError):
		make_diagnostic_archive(str(tmp_path / 'out.tar.gz'), str(root), {'include': ['results/*.log']})


def test_file_size_guard_omits_large_file(tmp_path):
	root = make_workspace(tmp_path)
	archive = tmp_path / 'out.tar.gz'
	make_diagnostic_archive(str(archive), str(root), {
		'include': ['results/IMAGES/image.fits'],
		'max_file_bytes': 100,
	})
	with tarfile.open(archive, 'r:gz') as tar:
		assert not any(name.endswith('image.fits') for name in tar.getnames())
		manifest = json.load(tar.extractfile(root.name + '/archive_policy.json'))
		assert manifest['omitted_files'][0]['reason'] == 'file_size_limit'


def test_no_policy_does_not_archive_results(tmp_path):
	root = make_workspace(tmp_path)
	archive = tmp_path / 'out.tar.gz'
	make_diagnostic_archive(str(archive), str(root))
	with tarfile.open(archive, 'r:gz') as tar:
		assert set(tar.getnames()) == {
			root.name + '/input/staging.json',
			root.name + '/archive_policy.json',
		}

