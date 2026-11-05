
"""Regression tests for OXKAT preview artifact registration.

The full preview collection is stored under previews/all/.
Only files in previews/selected/ are individually registered.
"""

import pytest

from caesar_rest.app_configurators.oxkat import OxkatAppConfigurator
from caesar_rest.pipeline.artifacts.discovery import (
	ArtifactDiscoveryError,
	discover_artifacts,
	select_output_contract,
)


def _contract(stage):
	configurator = OxkatAppConfigurator()
	return select_output_contract(configurator.job_outputs, stage)


def _results(tmp_path):
	results = tmp_path / 'results'
	results.mkdir()

	(results / 'oxkat_manifest.json').write_text(
		'{}', encoding='utf-8'
	)
	(results / 'project_info.json').write_text(
		'{}', encoding='utf-8'
	)

	return results


def _previews(results):
	root = results / 'previews'

	for name in ('all', 'selected', 'logs', 'catalog'):
		(root / name).mkdir(parents=True)

	(root / 'image_qa.json').write_text(
		'{"products": []}', encoding='utf-8'
	)

	return root


def test_preview_contract_is_stage_scoped():
	for stage in ('FLAG', '2GC'):
		contract = _contract(stage)

		assert contract['image_qa']['path'] == (
			'previews/image_qa.json'
		)
		assert contract['image_previews']['glob'] == (
			'previews/selected/preview_*.png'
		)

		assert 'sourcefind_logs' in contract
		assert 'sourcefind_catalog_tables' in contract
		assert 'sourcefind_catalog_regions' in contract

	for stage in ('GET_INFO', '1GC'):
		contract = _contract(stage)

		assert 'image_qa' not in contract
		assert 'image_previews' not in contract
		assert 'sourcefind_logs' not in contract


@pytest.mark.parametrize('stage', ['FLAG', '2GC'])
def test_discovery_registers_preview_files_and_qa(tmp_path, stage):
	results = _results(tmp_path)

	images = results / 'IMAGES'
	images.mkdir()
	(images / 'scientific-MFS-image.fits').write_bytes(b'fits')

	root = _previews(results)

	(root / 'all' / 'preview_image__overview.png').write_bytes(
		b'full'
	)
	(root / 'selected' / 'preview_image__overview.png').write_bytes(
		b'png'
	)
	(root / 'logs' / 'sourcefind_image__BANE.log').write_text(
		'ok', encoding='utf-8'
	)
	(root / 'catalog' / 'sourcefind_image__components_ascii.tab').write_text(
		'data', encoding='utf-8'
	)
	(root / 'catalog' / 'sourcefind_image__components_ds9.reg').write_text(
		'fk5', encoding='utf-8'
	)

	artifacts = discover_artifacts(
		str(tmp_path), _contract(stage)
	)

	by_name = {}
	for artifact in artifacts:
		by_name.setdefault(artifact['name'], []).append(artifact)

	assert len(by_name['image_qa']) == 1
	assert len(by_name['image_previews']) == 1
	assert len(by_name['sourcefind_logs']) == 1
	assert len(by_name['sourcefind_catalog_tables']) == 1
	assert len(by_name['sourcefind_catalog_regions']) == 1

	assert by_name['image_qa'][0]['relative_path'] == (
		'results/previews/image_qa.json'
	)
	assert by_name['image_previews'][0]['relative_path'] == (
		'results/previews/selected/preview_image__overview.png'
	)

	assert not any(
		artifact['relative_path'].startswith('results/previews/all/')
		for artifact in artifacts
	)


def test_historical_run_without_previews_is_supported(tmp_path):
	results = _results(tmp_path)
	(results / 'IMAGES').mkdir()

	artifacts = discover_artifacts(
		str(tmp_path), _contract('FLAG')
	)

	assert not any(
		artifact['name'] in ('image_qa', 'image_previews')
		for artifact in artifacts
	)


def test_746_generated_previews_only_selected_are_registered(tmp_path):
	results = _results(tmp_path)
	(results / 'IMAGES').mkdir()
	root = _previews(results)

	for index in range(746):
		filename = 'preview_image_%04d__overview.png' % index

		(root / 'all' / filename).write_bytes(b'png')

		if index < 40:
			(root / 'selected' / filename).write_bytes(b'png')

	artifacts = discover_artifacts(
		str(tmp_path), _contract('2GC')
	)

	assert sum(
		artifact['name'] == 'image_previews'
		for artifact in artifacts
	) == 40

	assert sum(
		artifact['name'] == 'image_qa'
		for artifact in artifacts
	) == 1


def test_preview_symlink_is_rejected(tmp_path):
	results = _results(tmp_path)
	root = _previews(results)

	outside = tmp_path / 'outside.png'
	outside.write_bytes(b'private')

	(root / 'selected' / 'preview_bad__overview.png').symlink_to(
		outside
	)

	with pytest.raises(ArtifactDiscoveryError, match='Symlink'):
		discover_artifacts(
			str(tmp_path), _contract('FLAG')
	)

