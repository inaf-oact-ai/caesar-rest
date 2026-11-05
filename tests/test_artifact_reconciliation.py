
"""Regression tests for append-only retained Pipeline V2 artifact recovery."""

import copy
import os

import pytest

from caesar_rest.pipeline.artifacts import reconciliation as subject


class FakeRuns:
	def __init__(self, run):
		self.run = run
		self.updates = 0

	def update_one(self, query, update):
		for key, expected in query.items():
			if self.run.get(key) != expected:
				return type('Result', (), {'modified_count': 0})()
		self.run.update(copy.deepcopy(update['$set']))
		self.updates += 1
		return type('Result', (), {'modified_count': 1})()


class FakeDB:
	def __init__(self, run):
		self.pipeline_runs = FakeRuns(run)


def old_artifact():
	return {
		'name': 'original',
		'relative_path': 'results/original.log',
		'type': 'text/plain',
		'size_bytes': 3,
	}


def new_artifact(name='preview'):
	return {
		'name': name,
		'relative_path': 'results/previews/selected/preview_1.png',
		'type': 'image/png',
		'size_bytes': 4,
	}


def make_fixture(tmp_path, monkeypatch, discovered=None):
	base = tmp_path / 'retained'
	base.mkdir()
	(base / '.retention.lock').write_bytes(b'')

	workspace = tmp_path / 'job'
	workspace.mkdir()

	run = {
		'_id': 'mongo-id',
		'owner': 'owner',
		'pipeline_id': 'pipeline',
		'node_id': 'stage',
		'run_id': 'run',
		'job_id': 'job',
		'application': 'fake',
		'status': 'COMPLETED',
		'job_state': 'SUCCESS',
		'job_exit_code': 0,
		'artifacts_registered_at': 'timestamp',
		'artifact_workspace': str(workspace),
		'retention_status': 'READY',
		'artifacts': [old_artifact()],
		'retained_artifacts': [
			{
				'index': 0,
				'sha256': 'a' * 64,
				'size_bytes': 3,
			},
		],
		'parameters': {'stage': '2GC'},
	}

	db = FakeDB(run)

	monkeypatch.setattr(
		subject,
		'_load_verified_run',
		lambda dbarg, *args: (
			copy.deepcopy(dbarg.pipeline_runs.run),
			str(workspace),
		),
	)

	monkeypatch.setattr(
		subject,
		'_check_existing',
		lambda *args: None,
	)

	monkeypatch.setattr(
		subject,
		'_discover',
		lambda *args: copy.deepcopy(
			discovered if discovered is not None
			else [old_artifact(), new_artifact()]
		),
	)

	monkeypatch.setattr(
		subject.retention,
		'retained_directory',
		lambda *args: str(base),
	)

	monkeypatch.setattr(
		subject.manager,
		'utcnow',
		lambda: 'reconciled-timestamp',
	)

	return db, base


def run_reconciliation(db, base, dry_run=True):
	return subject.reconcile_retained_run(
		db,
		'owner',
		'pipeline',
		'stage',
		'run',
		str(base),
		dry_run=dry_run,
	)


def test_plan_preserves_existing_index_and_appends_missing(tmp_path, monkeypatch):
	db, base = make_fixture(tmp_path, monkeypatch)

	result = run_reconciliation(db, base)

	assert result['existing'] == 1
	assert result['additional'] == 1
	assert result['new_artifacts'][0]['index'] == 1
	assert db.pipeline_runs.updates == 0


def test_reconciliation_publishes_both_arrays_together(tmp_path, monkeypatch):
	db, base = make_fixture(tmp_path, monkeypatch)
	copied = []

	def fake_copy(dbarg, owner, transient, index, artifact, storage, limit):
		assert 'retained_artifacts' not in transient
		assert len(transient['artifacts']) == 2

		copied.append(index)
		(base / ('%04d' % index)).write_bytes(b'data')

		return {
			'index': index,
			'size_bytes': 4,
			'sha256': 'b' * 64,
		}

	monkeypatch.setattr(
		subject.directory_promotion,
		'_copy_file',
		fake_copy,
	)

	result = run_reconciliation(db, base, dry_run=False)

	assert result['committed'] is True
	assert copied == [1]
	assert db.pipeline_runs.updates == 1
	assert db.pipeline_runs.run['artifacts'][0] == old_artifact()
	assert db.pipeline_runs.run['retained_artifacts'][0]['sha256'] == 'a' * 64
	assert len(db.pipeline_runs.run['artifacts']) == 2
	assert len(db.pipeline_runs.run['retained_artifacts']) == 2


def test_rerun_is_idempotent(tmp_path, monkeypatch):
	db, base = make_fixture(tmp_path, monkeypatch)

	def fake_copy(dbarg, owner, transient, index, artifact, storage, limit):
		(base / ('%04d' % index)).write_bytes(b'data')

		return {
			'index': index,
			'size_bytes': 4,
			'sha256': 'b' * 64,
		}

	monkeypatch.setattr(
		subject.directory_promotion,
		'_copy_file',
		fake_copy,
	)

	run_reconciliation(db, base, dry_run=False)
	second = run_reconciliation(db, base, dry_run=False)

	assert second['additional'] == 0
	assert db.pipeline_runs.updates == 1


def test_resume_requires_verification_of_prepared_file(tmp_path, monkeypatch):
	db, base = make_fixture(tmp_path, monkeypatch)

	(base / '0001').write_bytes(b'data')
	calls = []

	def reuse(dbarg, owner, transient, index, artifact, storage, limit):
		calls.append(index)

		return {
			'index': index,
			'size_bytes': 4,
			'sha256': 'b' * 64,
		}

	monkeypatch.setattr(
		subject.resume,
		'reuse_file',
		reuse,
	)

	monkeypatch.setattr(
		subject.directory_promotion,
		'_copy_file',
		lambda *args: pytest.fail(
			'Unexpected replacement of prepared file'
		),
	)

	run_reconciliation(db, base, dry_run=False)

	assert calls == [1]


def test_reject_changed_existing_metadata():
	run = {'artifacts': [old_artifact()]}

	changed = old_artifact()
	changed['size_bytes'] = 100

	with pytest.raises(subject.ArtifactReconciliationError):
		subject._plan(run, [changed])


def test_refuse_new_directory_artifacts():
	run = {'artifacts': [old_artifact()]}

	with pytest.raises(subject.ArtifactReconciliationError):
		subject._plan(
			run,
			[
				old_artifact(),
				{
					'name': 'large',
					'relative_path': 'results/IMAGES',
					'kind': 'directory',
					'size_bytes': 9,
				},
			],
		)


def test_reject_duplicate_discovered_paths():
	run = {'artifacts': [old_artifact()]}

	with pytest.raises(subject.ArtifactReconciliationError):
		subject._plan(
			run,
			[
				old_artifact(),
				new_artifact(),
				new_artifact(),
			],
		)


def test_failed_compare_and_set_does_not_publish(tmp_path, monkeypatch):
	db, base = make_fixture(tmp_path, monkeypatch)

	monkeypatch.setattr(
		subject.directory_promotion,
		'_copy_file',
		lambda *args: {
			'index': 1,
			'size_bytes': 4,
			'sha256': 'b' * 64,
		},
	)

	# Simulate a concurrent record mutation before MongoDB CAS.
	orig_update = db.pipeline_runs.update_one

	def fail_update(query, update):
		db.pipeline_runs.run['artifacts'] = []
		return orig_update(query, update)

	db.pipeline_runs.update_one = fail_update

	with pytest.raises(
		subject.ArtifactReconciliationError,
		match='Concurrent update',
	):
		run_reconciliation(db, base, dry_run=False)

	assert db.pipeline_runs.updates == 0

