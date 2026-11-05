#!/usr/bin/env python3
"""Safely replace selected completed Pipeline V2 job archives with diagnostics.

Dry-run by default. Requires CAESAR_REST_DBHOST, CAESAR_REST_DBPORT,
CAESAR_REST_DBNAME and the normal CAESAR-REST Python environment.

Run only when the job monitor is not actively writing the selected archives,
and when no clients are downloading those archives.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import tarfile
from pathlib import Path

from pymongo import MongoClient
from caesar_rest.job_configurator import JobConfigurator
from caesar_rest.pipeline.archive import make_diagnostic_archive
from caesar_rest.pipeline.artifacts import directory_integrity
from caesar_rest.pipeline.artifacts import retention
from caesar_rest.pipeline.staging.workspace import workspace_for_job

_ID = re.compile(r'^[a-zA-Z0-9_-]{1,128}$')


def require(condition, message):
	if not condition:
		raise RuntimeError(message)


def digest_file(path):
	h = hashlib.sha256()
	with open(path, 'rb') as stream:
		while True:
			block = stream.read(1024 * 1024)
			if not block:
				break
			h.update(block)
	return h.hexdigest()


def inspect_job(db, owner, job_id, retention_root):
	job = db[owner + '.jobs'].find_one({'job_id': job_id})
	require(job is not None, 'Job not found')
	require(job.get('execution_mode') == 'staged_container', 'Not a staged Pipeline V2 job')
	require(job.get('state') == 'SUCCESS' and str(job.get('exit_code')) == '0', 'Job not successful')
	pipeline_id = job.get('pipeline_id')
	run_id = job.get('run_id')
	app = job.get('app')
	require(all(isinstance(v, str) and v for v in (pipeline_id, run_id, app)), 'Job identity incomplete')
	run = db.pipeline_runs.find_one({
		'owner': owner, 'pipeline_id': pipeline_id, 'run_id': run_id,
		'job_id': job_id, 'application': app,
	})
	require(run is not None and run.get('status') == 'COMPLETED', 'Completed run unavailable')
	require(run.get('artifacts_registered_at') is not None, 'Artifacts not registered')
	require(run.get('retention_status') not in ('PENDING', 'COPYING', 'FAILED'), 'Retention not complete')
	artifacts = run.get('artifacts')
	records = run.get('retained_artifacts')
	require(isinstance(artifacts, list) and artifacts and isinstance(records, list), 'Retention records missing')
	require(len(artifacts) == len(records), 'Incomplete retention records')
	require(all(isinstance(record, dict) and record.get('index') == i
		for i, record in enumerate(records)), 'Retention indices not aligned')

	workspace = workspace_for_job(job.get('job_top_dir'), job_id)
	require(run.get('artifact_workspace') == workspace, 'Registered workspace mismatch')
	require(os.path.isdir(workspace) and not os.path.islink(workspace), 'Job workspace unavailable')

	base = retention.retained_directory(retention_root, owner, pipeline_id, run_id)
	require(os.path.isdir(base) and not os.path.islink(base), 'Retention directory unavailable')
	for index, (artifact, record) in enumerate(zip(artifacts, records)):
		require(artifact.get('size_bytes') == record.get('size_bytes'),
			'Retained size mismatch at index %d' % index)
		if artifact.get('kind') == 'directory':
			directory_integrity.verify_directory_manifest(base, index, record)
		else:
			path = os.path.join(base, '%04d' % index)
			require(os.path.isfile(path) and not os.path.islink(path),
				'Retained file unavailable at index %d' % index)
			require(os.stat(path, follow_symlinks=False).st_size == record['size_bytes'],
				'Retained file size changed at index %d' % index)
			require(digest_file(path) == record.get('sha256'),
				'Retained file hash mismatch at index %d' % index)

	desc = JobConfigurator().get_app_description(app)
	require(isinstance(desc, dict) and isinstance(desc.get('archive_policy'), dict),
		'Application archive policy unavailable')
	archive = os.path.join(workspace, 'job_' + job_id + '.tar.gz')
	require(os.path.isfile(archive) and not os.path.islink(archive), 'Existing archive unavailable')
	return workspace, archive, desc['archive_policy'], len(artifacts)


def validate_archive(path, workspace):
	root = Path(workspace)
	prefix = root.name + '/'
	with tarfile.open(path, 'r:gz') as tar:
		members = tar.getmembers()
		member_map = {m.name: m for m in members}
		require(len(member_map) == len(members), 'Archive has duplicate names')
		policy_member = member_map.get(prefix + 'archive_policy.json')
		require(policy_member is not None and policy_member.isfile(), 'Archive policy manifest missing')
		manifest = json.load(tar.extractfile(policy_member))
		require(manifest.get('schema') == 'caesar.pipeline-job-archive.v1', 'Unrecognized archive policy manifest')
		require(manifest.get('complete_scientific_output') is False, 'Not a diagnostic archive')
		require(not manifest.get('omitted_files'), 'Diagnostic files were omitted; refusing replacement')
		included = manifest.get('included_files')
		require(isinstance(included, list) and len(included) == len(set(included)), 'Invalid inclusion manifest')
		expected_names = set(prefix + relative for relative in included)
		require(set(member_map) == expected_names | {prefix + 'archive_policy.json'}, 'Unexpected archive members')
		for relative in included:
			require(relative.startswith('results/') or relative == 'input/staging.json',
				'Unexpected included path')
			member = member_map[prefix + relative]
			require(member.isfile() and not member.issym() and not member.islnk(),
				'Archive contains non-file member')
			original = root / relative
			require(original.is_file() and not original.is_symlink(), 'Archived source unavailable')
			require(member.size == original.stat().st_size, 'Archived source size mismatch')
			source_digest = digest_file(original)
			h = hashlib.sha256()
			with tar.extractfile(member) as stream:
				while True:
					block = stream.read(1024 * 1024)
					if not block:
						break
					h.update(block)
			require(h.hexdigest() == source_digest, 'Archived source checksum mismatch')
	return len(included)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--owner', required=True)
	parser.add_argument('--retention-root', required=True)
	parser.add_argument('--job-id', action='append', required=True)
	parser.add_argument('--apply', action='store_true', help='Replace archives; default is read-only')
	args = parser.parse_args()
	require(_ID.fullmatch(args.owner) is not None, 'Invalid owner')
	require(all(_ID.fullmatch(job_id) is not None for job_id in args.job_id), 'Invalid job ID')
	require(os.path.isabs(args.retention_root), 'Retention root must be absolute')
	client = MongoClient(os.environ['CAESAR_REST_DBHOST'], int(os.environ['CAESAR_REST_DBPORT']))
	try:
		db = client[os.environ['CAESAR_REST_DBNAME']]
		for job_id in args.job_id:
			print('Job %s:' % job_id, flush=True)
			workspace, archive, policy, count = inspect_job(db, args.owner, job_id, args.retention_root)
			old_size = os.stat(archive, follow_symlinks=False).st_size
			print('  validated retained artifacts=%d; original archive=%.2f GiB' %
				(count, old_size / (1024 ** 3)), flush=True)
			if not args.apply:
				print('  DRY RUN: eligible; no archive created or modified', flush=True)
				continue
			# Write a separate candidate; the archive builder publishes it atomically.
			candidate = os.path.join(workspace, '.diagnostic-migration-' + job_id + '.tar.gz')
			require(not os.path.lexists(candidate), 'Migration candidate already exists; inspect before retry')
			try:
				make_diagnostic_archive(candidate, workspace, policy)
				included = validate_archive(candidate, workspace)
				new_size = os.stat(candidate, follow_symlinks=False).st_size
				require(new_size < old_size, 'Diagnostic archive is not smaller')
				# Do not replace if another process changed the archive during migration.
				require(os.path.isfile(archive) and not os.path.islink(archive) and
					os.stat(archive, follow_symlinks=False).st_size == old_size,
					'Original archive changed while migrating')
				os.replace(candidate, archive)
				print('  REPLACED: %d diagnostic files, %.2f MiB (saved %.2f GiB)' %
					(included, new_size / (1024 ** 2), (old_size - new_size) / (1024 ** 3)), flush=True)
			finally:
				if os.path.exists(candidate):
					os.unlink(candidate)
	finally:
		client.close()


if __name__ == '__main__':
	main()
