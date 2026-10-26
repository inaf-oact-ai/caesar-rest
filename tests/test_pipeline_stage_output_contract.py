"""Regression tests for generic, stage-aware pipeline output contracts."""

import pytest

from caesar_rest.pipeline.artifacts import discovery


def _contract():
	return {
		'manifest': {
			'path': 'manifest.json', 'glob': None,
			'required': True,
		},
		'first_stage_ms': {
			'path': None, 'glob': '*.ms', 'kind': 'directory',
			'stages': ['FIRST'], 'required': False,
		},
		'second_stage_ms': {
			'path': None, 'glob': '*.ms', 'kind': 'directory',
			'stages': ['SECOND'], 'required': False,
		},
		'shared_log': {
			'path': 'run.log', 'glob': None,
			'stages': ['FIRST', 'SECOND'], 'required': False,
		},
	}


def test_stage_selection_excludes_other_stage_outputs():
	contract = _contract()
	first = discovery.select_output_contract(contract, 'FIRST')
	second = discovery.select_output_contract(contract, 'SECOND')
	assert set(first) == {'manifest', 'first_stage_ms', 'shared_log'}
	assert set(second) == {'manifest', 'second_stage_ms', 'shared_log'}
	assert contract == _contract()  # Selection must not mutate the contract.


def test_unscoped_outputs_are_available_without_stage():
	selected = discovery.select_output_contract(_contract(), None)
	assert set(selected) == {'manifest'}


def test_legacy_contract_without_stages_is_unchanged():
	contract = {
		'manifest': {'path': 'manifest.json', 'glob': None},
		'log': {'path': None, 'glob': '*.log'},
	}
	assert discovery.select_output_contract(contract, None) == contract
	assert discovery.select_output_contract(contract, 'ANY_STAGE') == contract


@pytest.mark.parametrize('stages', [
	[],
	'FIRST',
	['FIRST', 'FIRST'],
	['FIRST', ''],
	['FIRST', None],
	['FIRST', 123],
	{'FIRST'},
])
def test_invalid_stage_declarations_are_rejected(stages):
	contract = {'data': {'path': 'data.txt', 'glob': None, 'stages': stages}}
	with pytest.raises(discovery.ArtifactDiscoveryError):
		discovery.select_output_contract(contract, 'FIRST')


def test_overlapping_ms_globs_are_safe_after_stage_selection(tmp_path):
	workspace = tmp_path / 'workspace'
	results = workspace / 'results'
	results.mkdir(parents=True)
	(results / 'manifest.json').write_text('{}', encoding='utf-8')
	(results / 'target.ms').mkdir()

	first_contract = discovery.select_output_contract(_contract(), 'FIRST')
	second_contract = discovery.select_output_contract(_contract(), 'SECOND')

	first = discovery.discover_artifacts(str(workspace), first_contract)
	second = discovery.discover_artifacts(str(workspace), second_contract)

	assert [a['name'] for a in first] == ['first_stage_ms', 'manifest']
	assert [a['name'] for a in second] == ['manifest', 'second_stage_ms']
	assert first[0]['kind'] == 'directory'
	assert second[1]['kind'] == 'directory'
	

def test_registration_uses_persisted_stage(monkeypatch):
	from types import SimpleNamespace
	from caesar_rest.pipeline.artifacts import registration

	run = {
		'application': 'oxkat',
		'parameters': {'stage': 'FLAG'},
		'status': 'COMPLETED',
	}

	class FakeRuns:
		def find_one(self, query):
			return run

	db = SimpleNamespace(pipeline_runs=FakeRuns())

	class FakeJobConfigurator:
		def get_app_description(self, app_name):
			assert app_name == 'oxkat'
			return {'job_outputs': _contract()}

	monkeypatch.setattr(
		registration,
		'JobConfigurator',
		lambda: FakeJobConfigurator()
	)

	captured = {}

	def fake_register(db_arg, owner, pipeline_id, run_id, job_id, contract):
		captured['contract'] = contract
		return True

	monkeypatch.setattr(
		registration,
		'register_completed_run',
		fake_register
	)

	assert registration.register_using_job_config(
		db, 'owner', 'pipeline', 'run', 'job'
	)

	assert set(captured['contract']) == {'manifest'}

