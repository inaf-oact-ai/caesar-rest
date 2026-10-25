"""Standalone CAESAR-REST pipeline artifact retention worker.

Run independently of the job monitor and REST server. Completed, registered,
unretained pipeline runs provide a durable MongoDB-backed work queue.
Deploy exactly one instance initially; the existing per-run filesystem lock
still protects overlapping retention requests.
"""
import argparse
import logging
import os
import signal
import time
from datetime import datetime, timezone

from pymongo import MongoClient

from caesar_rest.pipeline.artifacts import retention


STOP = False


def request_stop(signum, frame):
	global STOP
	STOP = True


def utcnow():
	return datetime.now(timezone.utc)


def process_one(db, root, limits):
	"""Process at most one pending run; return True if work was found."""
	query = {
		'status': 'COMPLETED',
		'artifacts_registered_at': {'$exists': True},
		'artifacts.0': {'$exists': True},
		'retained_artifacts': {'$exists': False},
		'$or': [
			{'retention_status': {'$exists': False}},
			{'retention_status': 'PENDING'},
		]
	}
	run = db.pipeline_runs.find_one_and_update(
		query,
		{'$set': {'retention_status': 'COPYING', 'retention_started_at': utcnow()},
		 '$unset': {'retention_error': ''}},
		sort=[('artifacts_registered_at', 1)]
	)
	if run is None:
		return False
	identity = {'_id': run['_id'], 'retention_status': 'COPYING'}
	try:
		result = retention.promote_run(
			db, run['owner'], run['pipeline_id'], run['node_id'],
			run['run_id'], root,
			limits['file_bytes'], limits['directory_bytes'],
			limits['directory_entries'], limits['directory_depth']
		)
		db.pipeline_runs.update_one(identity, {'$set': {
			'retention_status': 'READY', 'retention_finished_at': utcnow()
		}})
		logging.info('Retained run %s: %s', run['run_id'], result)
	except Exception as exc:
		logging.exception('Retention failed for run %s', run['run_id'])
		db.pipeline_runs.update_one(identity, {'$set': {
			'retention_status': 'FAILED', 'retention_finished_at': utcnow(),
			'retention_error': str(exc)[:1000]
		}})
	return True


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--dbhost', default='localhost')
	parser.add_argument('--dbport', type=int, default=27017)
	parser.add_argument('--dbname', default='caesardb')
	parser.add_argument('--retention-root', required=True)
	parser.add_argument('--poll-seconds', type=int, default=30)
	parser.add_argument('--max-file-bytes', type=int, default=1024 ** 3)
	parser.add_argument('--max-directory-bytes', type=int, default=1024 ** 4)
	parser.add_argument('--max-directory-entries', type=int, default=100000)
	parser.add_argument('--max-directory-depth', type=int, default=16)
	args = parser.parse_args()
	if (not os.path.isabs(args.retention_root)
			or os.path.normpath(args.retention_root) != args.retention_root
			or args.retention_root == '/'):
		parser.error('Invalid retention root')
	if min(args.poll_seconds, args.max_file_bytes, args.max_directory_bytes,
			args.max_directory_entries, args.max_directory_depth) < 1:
		parser.error('Polling interval and retention limits must be positive')
	logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
	client = MongoClient(args.dbhost, args.dbport, serverSelectionTimeoutMS=10000)
	client.admin.command('ping')
	db = client[args.dbname]
	limits = {
		'file_bytes': args.max_file_bytes,
		'directory_bytes': args.max_directory_bytes,
		'directory_entries': args.max_directory_entries,
		'directory_depth': args.max_directory_depth,
	}
	for sig in (signal.SIGINT, signal.SIGTERM):
		signal.signal(sig, request_stop)
	logging.info('Artifact retention worker started (root=%s)', args.retention_root)
	while not STOP:
		try:
			if process_one(db, args.retention_root, limits):
				continue
		except Exception:
			logging.exception('Retention worker polling failure')
		for _ in range(args.poll_seconds):
			if STOP:
				break
			time.sleep(1)
	logging.info('Artifact retention worker stopped')


if __name__ == '__main__':
	main()
