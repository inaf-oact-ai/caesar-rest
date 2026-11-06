"""Regression coverage for narrowly scoped nested OXKAT artifact globs.

Install into caesar-rest/tests/ and run in the CAESAR-REST Python environment.
"""
import pytest

from caesar_rest.pipeline.artifacts.discovery import (
	ArtifactDiscoveryError, discover_artifacts, select_output_contract,
)


def _contract():
	return {
		'image_qa': {'path': 'previews/image_qa.json', 'stages': ['FLAG', '2GC']},
		'image_previews': {'glob': 'previews/selected/preview_*.png', 'stages': ['FLAG', '2GC']},
		'sourcefind_logs': {'glob': 'previews/logs/sourcefind_*.log', 'stages': ['FLAG', '2GC']},
		'catalog_tables': {'glob': 'previews/catalog/sourcefind_*.tab', 'stages': ['FLAG', '2GC']},
		'catalog_regions': {'glob': 'previews/catalog/sourcefind_*.reg', 'stages': ['FLAG', '2GC']},
	}


def _workspace(tmp_path):
	results = tmp_path / 'results'
	for sub in ('previews/selected', 'previews/all', 'previews/catalog', 'previews/logs'):
		(results / sub).mkdir(parents=True)
	(results / 'previews/image_qa.json').write_text('{}')
	(results / 'previews/selected/preview_a__overview.png').write_bytes(b'png')
	(results / 'previews/all/preview_a__overview.png').write_bytes(b'png')
	(results / 'previews/logs/sourcefind_a__BANE.log').write_text('done')
	(results / 'previews/catalog/sourcefind_a__components.tab').write_text('table')
	(results / 'previews/catalog/sourcefind_a__components.reg').write_text('regions')
	return results


def test_nested_selection(tmp_path):
	_workspace(tmp_path)
	artifacts = discover_artifacts(str(tmp_path), select_output_contract(_contract(), 'FLAG'))
	paths = {a['relative_path'] for a in artifacts}
	assert paths == {
		'results/previews/image_qa.json',
		'results/previews/selected/preview_a__overview.png',
		'results/previews/logs/sourcefind_a__BANE.log',
		'results/previews/catalog/sourcefind_a__components.tab',
		'results/previews/catalog/sourcefind_a__components.reg',
	}
	assert not discover_artifacts(str(tmp_path), select_output_contract(_contract(), 'GET_INFO'))


def test_nested_symlink_intermediate_rejected(tmp_path):
	results = _workspace(tmp_path)
	(results / 'previews/selected').rename(results / 'previews/selected_real')
	(results / 'previews/selected').symlink_to(results / 'previews/selected_real')
	with pytest.raises(ArtifactDiscoveryError, match='Symlink'):
		discover_artifacts(str(tmp_path), select_output_contract(_contract(), 'FLAG'))


@pytest.mark.parametrize('bad', [
	'previews/../selected/preview_*.png',
	'previews/**/preview_*.png',
	'pre*/selected/preview_*.png',
	'previews/selected/../preview_*.png',
])
def test_invalid_nested_glob_rejected(tmp_path, bad):
	_workspace(tmp_path)
	with pytest.raises(ArtifactDiscoveryError):
		discover_artifacts(str(tmp_path), {'bad': {'glob': bad}})
