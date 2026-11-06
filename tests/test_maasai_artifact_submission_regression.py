"""R4C.4B final synthetic cross-boundary regression.

Run: python -m pytest -q tests/test_maasai_artifact_submission_regression.py

Uses real directory-retention, manifest verification, named-input resolution,
artifact binding and submission claim functions. No MongoDB or Slurm.

IMPORTANT: At registration time directory bindings verify the retained
MANIFEST, not the bytes of every file. Full byte verification belongs to
private-copy staging. This suite explicitly tests that boundary.
"""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import binding, retention
from caesar_rest.pipeline.artifacts.directory_integrity import (
	DirectoryIntegrityError, verify_directory_artifact,
)
from caesar_rest.pipeline.artifacts.directory_retention import copy_directory_artifact
from caesar_rest.pipeline.submission import job_binding


OWNER = 'maasai-test-owner'
PIPELINE = 'pipeline-test'


class MemoryRuns:
	"""Minimal owner-scoped, conditional-update stand-in for pipeline_runs."""

	def __init__(self, runs):
		self.records = {run['run_id']: deepcopy(run) for run in runs}

	@staticmethod
	def _value(document, field):
		parts = field.split('.')
		value = document
		for part in parts:
			if not isinstance(value, dict) or part not in value:
				return False, None
			value = value[part]
		return True, value

	@classmethod
	def _matches(cls, document, query):
		for key, wanted in query.items():
			found, current = cls._value(document, key)
			if isinstance(wanted, dict) and '$exists' in wanted:
				if found != wanted['$exists']:
					return False
			elif not found or current != wanted:
				return False
		return True

	def find_one(self, query):
		for record in self.records.values():
			if self._matches(record, query):
				return deepcopy(record)
		return None

	def update_one(self, query, update):
		for key, record in self.records.items():
			if not self._matches(record, query):
				continue
			for field, value in update.get('$set', {}).items():
				record[field] = deepcopy(value)
			for field in update.get('$unset', {}):
				record.pop(field, None)
			return SimpleNamespace(modified_count=1, matched_count=1)
		return SimpleNamespace(modified_count=0, matched_count=0)


@pytest.fixture
def directory_context(tmp_path, monkeypatch):
	"""Create a genuine retained directory and authenticated run records."""
	source = tmp_path / 'source-target.ms'
	source.mkdir()
	(source / 'table.dat').write_bytes(b'original-data')
	(source / 'ANTENNA').mkdir()
	(source / 'ANTENNA' / 'table.dat').write_bytes(b'antenna')

	base = tmp_path / 'retained'
	base.mkdir()
	expected = {
		'size_bytes': len(b'original-data') + len(b'antenna'),
		'file_count': 2, 'directory_count': 1,
	}
	copied = copy_directory_artifact(
		str(source), str(base / '0000'), expected,
		allow_locked_fallback=True,
	)
	manifest_bytes = json.dumps(
		copied['manifest'], sort_keys=True,
		separators=(',', ':'), ensure_ascii=False,
	).encode('utf-8')
	(base / '0000.manifest.json').write_bytes(manifest_bytes)
	record = {
		'index': 0, 'kind': 'directory',
		'manifest_name': '0000.manifest.json',
		'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
		**expected,
	}
	artifact = {
		'name': 'working_measurement_sets',
		'kind': 'directory',
		'relative_path': 'results/target_TARGET_A.ms',
		**expected,
	}
	source_run = {
		'owner': OWNER, 'pipeline_id': PIPELINE,
		'run_id': 'gc1', 'node_id': 'calibration',
		'application': 'oxkat', 'status': 'COMPLETED',
		'parameters': {'stage': '1GC'},
		'artifacts_registered_at': 'now',
		'artifacts': [artifact], 'retained_artifacts': [record],
	}
	second_run = deepcopy(source_run)
	second_run['run_id'] = 'gc2'
	runs = MemoryRuns([source_run, second_run])
	db = SimpleNamespace(pipeline_runs=runs)
	pipeline = {
		'owner': OWNER, 'pipeline_id': PIPELINE,
		'selections': {'calibration': {'run_id': 'gc1'}},
	}
	monkeypatch.setattr(
		retention, 'retained_directory',
		lambda root, owner, pipeline_id, run_id: str(base),
	)
	return SimpleNamespace(
		base=base, record=record, db=db, runs=runs,
		pipeline=pipeline, source=source_run,
	)


def named_binding(ctx):
	requests = binding.resolve_named_inputs(
		ctx.db, OWNER, PIPELINE,
		{'target_ms': {
			'node_id': 'calibration', 'selected': True,
			'artifact': 'working_measurement_sets',
		}},
		pipeline=ctx.pipeline,
	)
	return binding.bind_inputs(ctx.db, OWNER, PIPELINE, requests, str(ctx.base))


def test_selected_directory_binding_freezes_exact_identity(directory_context):
	ctx = directory_context
	frozen = named_binding(ctx)
	assert len(frozen) == 1
	assert frozen[0]['source_run_id'] == 'gc1'
	assert frozen[0]['artifact_index'] == 0
	assert frozen[0]['manifest_sha256'] == ctx.record['manifest_sha256']
	assert 'relative_path' not in frozen[0]
	assert 'storage_path' not in frozen[0]
	before = deepcopy(frozen)
	ctx.pipeline['selections']['calibration'] = {'run_id': 'gc2'}
	assert named_binding(ctx)[0]['source_run_id'] == 'gc2'
	assert frozen == before
	assert frozen[0]['source_run_id'] == 'gc1'


def test_missing_retention_rejected_without_downstream_binding(directory_context):
	ctx = directory_context
	ctx.runs.records['gc1']['retained_artifacts'] = None
	with pytest.raises(manager.PipelineError) as exc:
		named_binding(ctx)
	assert exc.value.status == 409


def test_corrupt_manifest_rejected_at_registration(directory_context):
	ctx = directory_context
	(ctx.base / '0000.manifest.json').write_bytes(b'{}')
	with pytest.raises(manager.PipelineError) as exc:
		named_binding(ctx)
	assert exc.value.status == 409


def test_missing_retained_directory_rejected(directory_context):
	ctx = directory_context
	(ctx.base / '0000' / 'table.dat').unlink()
	(ctx.base / '0000' / 'ANTENNA' / 'table.dat').unlink()
	(ctx.base / '0000' / 'ANTENNA').rmdir()
	(ctx.base / '0000').rmdir()
	with pytest.raises(manager.PipelineError) as exc:
		named_binding(ctx)
	assert exc.value.status == 409


def test_content_tampering_requires_full_staging_verification(directory_context):
	"""Manifest-only binding isn't a full byte-level integrity check."""
	ctx = directory_context
	(ctx.base / '0000' / 'table.dat').write_bytes(b'ORIGINAL-DATA')
	# Binding verifies the sidecar and retained-directory identity only.
	assert named_binding(ctx)[0]['source_run_id'] == 'gc1'
	# Full verification (used at private-copy staging) detects changed bytes.
	with pytest.raises(DirectoryIntegrityError):
		verify_directory_artifact(str(ctx.base), 0, ctx.record)


@pytest.fixture
def submission_context(monkeypatch):
	def planned(run_id, target):
		return {
			'owner': OWNER, 'pipeline_id': PIPELINE,
			'run_id': run_id, 'node_id': 'stage_flag_' + target,
			'application': 'oxkat', 'status': 'PLANNED',
			'parameters': {'stage': 'FLAG', 'target': target},
			'input_artifacts': [{'source_run_id': 'gc1', 'artifact_index': 0}],
		}
	runs = MemoryRuns([
		planned('flag-a', 'TARGET_A'),
		planned('flag-b', 'TARGET_B'),
		planned('flag-a-retry', 'TARGET_A'),
	])
	monkeypatch.setattr(manager, 'collections', lambda: (None, runs, None))
	monkeypatch.setattr(
		manager, 'get_pipeline',
		lambda owner, pipeline_id: {'owner': owner, 'pipeline_id': pipeline_id},
	)
	return runs


def claim(run_id, target):
	return job_binding.claim_run(
		OWNER, PIPELINE, run_id, 'oxkat',
		{'stage': 'FLAG', 'target': target},
	)


def test_uncertain_submission_never_reclaims_same_run(submission_context):
	runs = submission_context
	first = claim('flag-a', 'TARGET_A')
	assets = {
		'version': 2, 'run_id': 'flag-a', 'job_id': 'synthetic-job-a',
		'worker_sha256': 'a' * 64,
	}
	intent = job_binding.begin_submission_intent(first, assets)
	job_binding.fail_submission(
		first, 'Simulated scheduler timeout', uncertain=True,
		job_id='synthetic-job-a',
	)
	original = deepcopy(runs.records['flag-a'])
	assert original['status'] == 'SUBMISSION_UNCERTAIN'
	assert original['submission_intent'] == intent
	assert manager.run_submission_info(original)['requires_reconciliation']
	assert not manager.run_submission_info(original)['retry_allowed']
	with pytest.raises(manager.PipelineError) as exc:
		claim('flag-a', 'TARGET_A')
	assert exc.value.status == 409
	assert runs.records['flag-a'] == original
	# Independent target is still claimable.
	other = claim('flag-b', 'TARGET_B')
	assert runs.records['flag-b']['status'] == 'SUBMITTING'
	assert other.run_id == 'flag-b'


def test_failed_experiment_is_immutable_and_new_run_can_be_claimed(submission_context):
	runs = submission_context
	# Simulate terminal scientific failure after a successful submission.
	runs.records['flag-a']['status'] = 'FAILED'
	failed = deepcopy(runs.records['flag-a'])
	with pytest.raises(manager.PipelineError) as exc:
		claim('flag-a', 'TARGET_A')
	assert exc.value.status == 409
	new = claim('flag-a-retry', 'TARGET_A')
	assert new.run_id == 'flag-a-retry'
	assert runs.records['flag-a']['status'] == 'FAILED'
	assert runs.records['flag-a']['input_artifacts'] == failed['input_artifacts']
	assert runs.records['flag-a-retry']['status'] == 'SUBMITTING'
	assert runs.records['flag-b']['status'] == 'PLANNED'
