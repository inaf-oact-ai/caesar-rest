#!/usr/bin/env python3
"""Standalone, local-container dataset inspection worker (R4C.2B.3).

Poll MongoDB for PENDING inspection records; claim one atomically; detect the
format using the B.2 factory; launch the configured Singularity image read-only;
validate bounded JSON; persist results guarded by generation and claim token.

This is deliberately independent of Flask/uWSGI, Slurm and OXKAT. Deploy one
instance initially. Lease expiry/retries/freshness policy are B.4 work.
"""

import argparse
import hashlib
import json
import logging
import os
import signal
import stat
import subprocess
import tempfile
import time
import uuid
import resource
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, ReturnDocument

from caesar_rest.dataset_inspection.registry import default_registry
from caesar_rest.dataset_inspection import lifecycle

STOP = False


class InspectionError(RuntimeError):
	pass

class TransientInspectionError(InspectionError):
	"""A temporary infrastructure failure eligible for bounded retry."""
	pass
	
def stop_worker(signum, frame):
	global STOP
	STOP = True


def utcnow():
	return datetime.now(timezone.utc)


def is_under(path, root):
	try:
		return os.path.commonpath((path, root)) == root
	except (ValueError, OSError):
		return False


def validate_dataset_path(doc, allowed_roots):
	"""Revalidate trusted registry path on each inspection, never client input."""
	path = doc.get('path')
	kind = doc.get('type')
	if not isinstance(path, str) or not os.path.isabs(path):
		raise InspectionError('Invalid registered dataset path')
	if kind not in ('directory', 'file'):
		raise InspectionError('Invalid registered dataset type')
	if any(c in path for c in (':', ',', '\n', '\r', '\x00')):
		raise InspectionError('Dataset path contains unsupported bind characters')
	resolved = os.path.realpath(path)
	if not any(is_under(resolved, root) for root in allowed_roots):
		raise InspectionError('Registered dataset is outside allowed roots')
	# No symlink to the dataset itself, including intermediate components.
	component = os.path.sep
	for part in Path(path).parts[1:]:
		component = os.path.join(component, part)
		if os.path.islink(component):
			raise InspectionError('Symlink in registered dataset path')
	try:
		info = os.stat(path, follow_symlinks=False)
	except OSError as exc:
		raise InspectionError('Registered dataset is unavailable') from exc
	if kind == 'directory' and not stat.S_ISDIR(info.st_mode):
		raise InspectionError('Registered dataset is not a directory')
	if kind == 'file' and not stat.S_ISREG(info.st_mode):
		raise InspectionError('Registered dataset is not a regular file')
	return resolved


def source_fingerprint(path, kind):
	"""Cheap change indicator, NOT a content checksum or immutability proof."""
	parts = [path]
	if kind == 'directory':
		parts.extend(os.path.join(path, name) for name in (
			'table.dat', 'FIELD/table.dat', 'STATE/table.dat',
			'OBSERVATION/table.dat', 'SPECTRAL_WINDOW/table.dat',
		))
	values = []
	for part in parts:
		try:
			info = os.stat(part, follow_symlinks=False)
		except OSError as exc:
			raise InspectionError('Dataset changed or became unavailable') from exc
		if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
			raise InspectionError('Unsupported entry in dataset fingerprint')
		values.append((os.path.relpath(part, path), info.st_dev, info.st_ino,
			info.st_size, info.st_mtime_ns))
	serialized = json.dumps(values, separators=(',', ':'))
	return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def run_container(image, singularity, dataset_path, output_dir, timeout):
	"""Execute a trusted inspector and terminate its process group on failure."""

	if os.path.islink(image):
		raise InspectionError('Inspector image path is a symlink')

	image = os.path.realpath(image)

	if not os.path.isfile(image):
		raise TransientInspectionError(
			'Configured inspector image unavailable'
		)

	command = [
		singularity, 'run', '--cleanenv', '--containall',
		'--bind', dataset_path + ':/input.ms:ro',
		'--bind', output_dir + ':/output:rw',
		image,
		'--input-ms=/input.ms',
		'--output-json=/output/inspection.json'
	]

	stdout_path = os.path.join(output_dir, 'container.stdout')
	stderr_path = os.path.join(output_dir, 'container.stderr')

	process = None
	deadline = time.monotonic() + timeout

	def limit_output_files():
		resource.setrlimit(
			resource.RLIMIT_FSIZE,
			(32 * 1024 * 1024, 32 * 1024 * 1024)
		)

	try:
		with open(stdout_path, 'wb') as stdout, \
				open(stderr_path, 'wb') as stderr:

			process = subprocess.Popen(
				command,
				stdout=stdout,
				stderr=stderr,
				start_new_session=True,
				preexec_fn=limit_output_files
			)

			while process.poll() is None:
				if STOP:
					raise TransientInspectionError(
						'Inspection interrupted by worker shutdown'
					)

				if time.monotonic() >= deadline:
					raise TransientInspectionError(
						'Inspector execution timed out'
					)

				time.sleep(0.5)

			if process.returncode != 0:
				with open(stderr_path, 'rb') as stream:
					stream.seek(
						max(0, os.path.getsize(stderr_path) - 1500)
					)
					tail = stream.read().decode(
						'utf-8', errors='replace'
					)

				logging.error(
					'Inspector failed (exit=%d, stderr_tail=%r)',
					process.returncode,
					tail
				)

				raise InspectionError(
					'Inspector exited with status %d'
					% process.returncode
				)

	except OSError as exc:
		raise TransientInspectionError(
			'Inspector runtime could not be launched'
		) from exc

	finally:
		if process is not None and process.poll() is None:
			try:
				os.killpg(process.pid, signal.SIGTERM)
				process.wait(timeout=5)
			except (ProcessLookupError, subprocess.TimeoutExpired):
				try:
					os.killpg(process.pid, signal.SIGKILL)
				except ProcessLookupError:
					pass

				process.wait()

def read_result(output_dir, spec, max_json_bytes):
	path = os.path.join(output_dir, 'inspection.json')
	try:
		info = os.lstat(path)
	except OSError as exc:
		raise InspectionError('Inspector did not produce a JSON result') from exc
	if not stat.S_ISREG(info.st_mode) or info.st_size > max_json_bytes:
		raise InspectionError('Inspector JSON output invalid or exceeds size limit')
	try:
		with open(path, 'rb') as stream:
			data = stream.read(max_json_bytes + 1)
		if len(data) > max_json_bytes:
			raise InspectionError('Inspector JSON exceeds size limit')
		doc = json.loads(data)
	except (OSError, UnicodeError, ValueError) as exc:
		raise InspectionError('Inspector output is not valid JSON') from exc
	if not isinstance(doc, dict):
		raise InspectionError('Inspector JSON must be an object')
	if doc.get('schema') != spec.output_schema or doc.get('format') != spec.format:
		raise InspectionError('Inspector output schema/format mismatch')
	identity = doc.get('inspector')
	if not isinstance(identity, dict) or identity.get('name') != spec.name:
		raise InspectionError('Inspector output identity mismatch')
	if not isinstance(doc.get('tables'), dict) or not isinstance(doc.get('field_observations'), dict):
		raise InspectionError('Inspector output missing expected scientific summaries')
	return doc


def process_one(db, factory, args, dataset_id=None):
	
	doc, token = lifecycle.claim_one(
		db,
		dataset_id,
		max_attempts=args.max_attempts,
		lease_seconds=args.lease_seconds
	)
	
	if doc is None:
		return False
		
	id_ = doc['dataset_id']
	generation = doc['inspection']['generation']
	guard = {
		'_id': doc['_id'],
		'enabled': True,
		'inspection.status': 'RUNNING',
		'inspection.generation': generation,
		'inspection.claim_token': token,
	}
	logging.info('Inspecting dataset=%s generation=%s', id_, generation)
	start = time.monotonic()
	try:
		path = validate_dataset_path(doc, args.allowed_roots)
		selection = factory.select(path, doc['type'], doc.get('format'))
		base = {
			'detected_format': selection.detected_format,
			'declared_format': selection.declared_format,
			'detection_evidence': selection.evidence,
		}
		
		if selection.status == 'MISMATCH':
			raise InspectionError('Declared dataset format conflicts with detected format')
			
		if selection.status == 'UNSUPPORTED':
			update = {'inspection.status': 'UNSUPPORTED',
				'inspection.finished_at': utcnow(), **{
				'inspection.' + key: value for key, value in base.items()}}
			result = db.datasets.update_one(guard, {
				'$set': update,
				'$unset': {
					'inspection.claim_token': '',
					'inspection.lease_until': '',
					'inspection.next_attempt_at': ''
				},
			})
			logging.info('Dataset=%s unsupported; published=%s', id_, result.modified_count == 1)
			return True
		
		before = source_fingerprint(path, doc['type'])
		spec = selection.inspector
		if spec.execution_backend != 'local':
			raise InspectionError('Unsupported inspector execution backend')
		
		with tempfile.TemporaryDirectory(prefix='caesar-inspection-', dir=args.work_root) as output:
			os.chmod(output, 0o700)
			run_container(spec.image, args.singularity, path, output, args.timeout_seconds)
			metadata = read_result(output, spec, args.max_json_bytes)
			
		after = source_fingerprint(path, doc['type'])
		
		if after != before:
			raise TransientInspectionError(
				'Dataset changed during inspection'
			)		
		
		update = {
			'inspection.status': 'READY',
			'inspection.finished_at': utcnow(),
			'inspection.inspector': {'name': spec.name,
				'version': metadata['inspector'].get('version')},
			'inspection.schema': spec.output_schema,
			'inspection.source_fingerprint': before,
			'inspection.metadata': metadata,
			**{'inspection.' + key: value for key, value in base.items()},
		}
		result = db.datasets.update_one(guard, {
			'$set': update,
			'$unset': {
				'inspection.claim_token': '',
				'inspection.lease_until': '',
				'inspection.next_attempt_at': '',
				'inspection.error': ''
			}
		})
		logging.info('Dataset=%s READY published=%s elapsed=%.1fs',
			id_, result.modified_count == 1, time.monotonic() - start)
			
	except Exception as exc:
		logging.exception(
			'Dataset inspection failed: dataset=%s',
			id_
		)

		state, published = lifecycle.fail_or_retry(
			db,
			guard,
			doc['inspection']['attempt'],
			str(exc),
			transient=isinstance(exc, TransientInspectionError),
			max_attempts=args.max_attempts,
			base_seconds=args.retry_base_seconds
		)

		logging.info(
			'Dataset=%s state=%s published=%s',
			id_,
			state,
			published
		)		
		
	return True


def parse_args():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--dbhost', default='localhost')
	parser.add_argument('--dbport', type=int, default=27017)
	parser.add_argument('--dbname', default='caesardb')
	parser.add_argument('--msv2-image', required=True)
	parser.add_argument('--allowed-root', action='append', required=True,
		help='Trusted dataset storage root; may be repeated')
	parser.add_argument('--work-root', required=True,
		help='Trusted local scratch directory; no input data stored here')
	parser.add_argument('--singularity', default='singularity')
	parser.add_argument('--poll-seconds', type=int, default=30)
	parser.add_argument('--timeout-seconds', type=int, default=900)
	parser.add_argument(
		'--lease-seconds',
		type=int,
		default=1200,
		help='Duration of one inspection claim lease'
	)

	parser.add_argument(
		'--max-attempts',
		type=int,
		default=3,
		help='Maximum inspection attempts per generation'
	)

	parser.add_argument(
		'--retry-base-seconds',
		type=int,
		default=30,
		help='Initial transient failure retry delay'
	)

	parser.add_argument(
		'--freshness-check-seconds',
		type=int,
		default=3600,
		help='Minimum interval between READY fingerprint checks'
	)	
	parser.add_argument('--max-json-bytes', type=int, default=4 * 1024 * 1024)
	parser.add_argument('--once', action='store_true',
		help='Process at most one pending dataset and exit')
	parser.add_argument('--dataset-id', default=None,
		help='In --once mode, claim only this dataset ID')
	args = parser.parse_args()
	if args.dataset_id and not args.once:
		parser.error('--dataset-id requires --once')
		
	if any(x <= 0 for x in (
		args.dbport,
		args.poll_seconds,
		args.timeout_seconds,
		args.max_json_bytes,
		args.lease_seconds,
		args.max_attempts,
		args.retry_base_seconds,
		args.freshness_check_seconds
	)):
		parser.error('Numeric limits must be positive')

	if args.lease_seconds <= args.timeout_seconds + 60:
		parser.error(
			'--lease-seconds must exceed '
			'--timeout-seconds by more than 60 seconds'
		)		
		
	if not os.path.isabs(args.msv2_image):
		parser.error('--msv2-image must be an absolute path')
	if not os.path.isabs(args.work_root) or not os.path.isdir(args.work_root):
		parser.error('--work-root must exist and be an absolute directory')
	if os.path.islink(args.work_root):
		parser.error('--work-root must not be a symlink')
	roots = []
	for root in args.allowed_root:
		if not os.path.isabs(root) or not os.path.isdir(root):
			parser.error('--allowed-root must be an existing absolute directory')
		roots.append(os.path.realpath(root))
	args.allowed_roots = roots
	return args


def main():
	
	args = parse_args()
	logging.basicConfig(level=logging.INFO,
		format='%(asctime)s %(levelname)s %(message)s')
	
	client = MongoClient(args.dbhost, args.dbport, serverSelectionTimeoutMS=10000)
	client.admin.command('ping')
	db = client[args.dbname]
	factory = default_registry(args.msv2_image)
	for signum in (signal.SIGINT, signal.SIGTERM):
		signal.signal(signum, stop_worker)
	
	if args.once:
		found = process_one(db, factory, args, args.dataset_id)
		logging.info('One-shot complete; pending dataset found=%s', found)
		return
		
	logging.info(
		'Dataset inspection worker started: '
		'database=%s, poll=%ds, timeout=%ds, '
		'lease=%ds, max_attempts=%d, freshness=%ds',
		args.dbname,
		args.poll_seconds,
		args.timeout_seconds,
		args.lease_seconds,
		args.max_attempts,
		args.freshness_check_seconds
	)

	heartbeat_interval = 300
	last_heartbeat = time.monotonic()

	while not STOP:
		try:
			if lifecycle.recover_one_expired(
				db,
				max_attempts=args.max_attempts,
				base_seconds=args.retry_base_seconds
			):
				continue

			if process_one(db, factory, args):
				continue

			if lifecycle.check_one_ready(
				db,
				validate_dataset_path,
				source_fingerprint,
				args.allowed_roots,
				check_interval_seconds=args.freshness_check_seconds
			):
				continue

		except Exception:
			logging.exception(
				'Dataset inspection worker polling failure'
			)

		now = time.monotonic()

		if now - last_heartbeat >= heartbeat_interval:
			logging.info(
				'Dataset inspection worker heartbeat: alive, polling MongoDB'
			)
			last_heartbeat = now

		for _ in range(args.poll_seconds):
			if STOP:
				break

			time.sleep(1)	
	
	logging.info('Dataset inspection worker stopped')


if __name__ == '__main__':
	main()
