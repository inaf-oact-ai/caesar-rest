#!/usr/bin/env python3
"""Run isolated MongoDB integration tests for CAESAR-REST inspection leases.

Uses a dedicated test database by default and removes only records it creates.
No scientific files, inspectors, or Singularity containers are accessed.
"""
import argparse
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
# Install this script in caesar-rest/tests before executing.
sys.path.insert(0, str(ROOT))
from caesar_rest.dataset_inspection import lifecycle


def ensure(condition, message):
	if not condition:
		raise AssertionError(message)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--dbhost', default='localhost')
	parser.add_argument('--dbport', type=int, default=27017)
	parser.add_argument('--dbname', default='caesar_inspection_lifecycle_test')
	args = parser.parse_args()
	if args.dbname == 'caesardb':
		parser.error('Refusing production database caesardb; use a dedicated test database')
	
	client = MongoClient(
		args.dbhost,
		args.dbport,
		serverSelectionTimeoutMS=5000,
		tz_aware=True,
		tzinfo=timezone.utc
	)
	client.admin.command('ping')
	db = client[args.dbname]
	prefix = 'r4c2b4_' + uuid.uuid4().hex
	ids = [prefix + '_lease', prefix + '_retry']
	base = datetime.now(timezone.utc).replace(microsecond=0)
	try:
		# Recovery: expired RUNNING -> PENDING, old claim must not publish.
		db.datasets.insert_one({
			'dataset_id': ids[0], 'enabled': True,
			'inspection': {
				'status': 'RUNNING', 'generation': 'g1', 'attempt': 1,
				'claim_token': 'stale-token',
				'lease_until': base - timedelta(seconds=1),
				'requested_at': base - timedelta(minutes=2),
			}
		})
		ensure(lifecycle.recover_one_expired(db, now=base, base_seconds=30), 'No expired lease recovered')
		doc = db.datasets.find_one({'dataset_id': ids[0]})
		ensure(doc['inspection']['status'] == 'PENDING', 'Expired claim not requeued')
		ensure(doc['inspection']['attempt'] == 1, 'Attempt counter changed during recovery')
		ensure(doc['inspection']['next_attempt_at'] == base + timedelta(seconds=30), 'Recovery backoff incorrect')
		ensure('claim_token' not in doc['inspection'], 'Expired claim token survived recovery')
		old_guard = {'_id': doc['_id'], 'inspection.status': 'RUNNING',
			'inspection.generation': 'g1', 'inspection.claim_token': 'stale-token'}
		ensure(db.datasets.update_one(old_guard, {'$set': {'inspection.status': 'READY'}}).matched_count == 0,
			'Stale claim unexpectedly published READY')
		claimed, token = lifecycle.claim_one(db, ids[0], now=base + timedelta(seconds=31), lease_seconds=1200)
		ensure(claimed is not None and claimed['inspection']['attempt'] == 2, 'Expired claim not reclaimable')
		ensure(token != 'stale-token', 'Claim token was reused')
		print('PASS: expired lease, retry delay, stale-claim protection, second claim')

		# Retry policy: transient failure first requeues, third attempt terminates.
		db.datasets.insert_one({
			'dataset_id': ids[1], 'enabled': True,
			'inspection': {
				'status': 'PENDING', 'generation': 'g2', 'attempt': 0,
				'requested_at': base,
			}
		})
		first, first_token = lifecycle.claim_one(db, ids[1], now=base, lease_seconds=1200)
		ensure(first is not None and first['inspection']['attempt'] == 1, 'First claim failed')
		state, published = lifecycle.fail_or_retry(db, lifecycle.claim_guard(first, first_token),
			1, 'temporary failure', transient=True, max_attempts=3, base_seconds=30, now=base)
		ensure((state, published) == ('PENDING', True), 'Transient first failure should requeue')
		ensure(lifecycle.claim_one(db, ids[1], now=base + timedelta(seconds=10))[0] is None,
			'Worker reclaimed before retry backoff elapsed')
		second, second_token = lifecycle.claim_one(db, ids[1], now=base + timedelta(seconds=31))
		ensure(second is not None and second['inspection']['attempt'] == 2, 'Second claim failed')
		state, published = lifecycle.fail_or_retry(db, lifecycle.claim_guard(second, second_token),
			2, 'temporary failure', transient=True, max_attempts=3, base_seconds=30,
			now=base + timedelta(seconds=31))
		ensure((state, published) == ('PENDING', True), 'Second transient failure should requeue')
		third, third_token = lifecycle.claim_one(db, ids[1], now=base + timedelta(seconds=92))
		ensure(third is not None and third['inspection']['attempt'] == 3, 'Third claim failed')
		state, published = lifecycle.fail_or_retry(db, lifecycle.claim_guard(third, third_token),
			3, 'temporary failure', transient=True, max_attempts=3, base_seconds=30,
			now=base + timedelta(seconds=92))
		ensure((state, published) == ('FAILED', True), 'Exhausted retries did not fail')
		ensure(lifecycle.claim_one(db, ids[1], now=base + timedelta(days=1))[0] is None,
			'FAILED inspection was incorrectly reclaimed')
		print('PASS: transient retry, backoff, max-attempt terminal failure')
		print('ALL MONGODB LIFECYCLE INTEGRATION CHECKS PASSED')
	finally:
		db.datasets.delete_many({'dataset_id': {'$in': ids}})
		client.close()


if __name__ == '__main__':
	main()
