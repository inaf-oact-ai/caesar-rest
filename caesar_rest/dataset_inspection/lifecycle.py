"""MongoDB inspection lifecycle for the independent dataset-inspection worker.

No Flask context, no scientific libraries and no Singularity dependency.
All mutations use generation/claim and state compare-and-set guards.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pymongo import ReturnDocument


def utcnow():
	return datetime.now(timezone.utc)


def claim_one(db, dataset_id=None, *, max_attempts=3, lease_seconds=1200, now=None):
	"""Claim exactly one eligible pending inspection using one atomic update."""
	now = now or utcnow()
	query = {
		'enabled': True,
		'inspection.status': 'PENDING',
		'inspection.generation': {'$type': 'string'},
		'inspection.attempt': {'$lt': max_attempts},
		'$or': [
			{'inspection.next_attempt_at': {'$exists': False}},
			{'inspection.next_attempt_at': {'$lte': now}},
		],
	}
	if dataset_id is not None:
		query['dataset_id'] = dataset_id
	token = uuid4().hex
	doc = db.datasets.find_one_and_update(
		query,
		{'$set': {
			'inspection.status': 'RUNNING',
			'inspection.claim_token': token,
			'inspection.started_at': now,
			'inspection.lease_until': now + timedelta(seconds=lease_seconds),
		}, '$inc': {'inspection.attempt': 1},
		 '$unset': {
			'inspection.error': '',
			'inspection.finished_at': '',
			'inspection.next_attempt_at': '',
		}},
		sort=[('inspection.requested_at', 1)],
		return_document=ReturnDocument.AFTER,
	)
	return doc, token


def claim_guard(doc, token):
	return {
		'_id': doc['_id'],
		'enabled': True,
		'inspection.status': 'RUNNING',
		'inspection.generation': doc['inspection']['generation'],
		'inspection.claim_token': token,
	}


def retry_delay(attempt, base_seconds=30, cap_seconds=3600):
	return min(cap_seconds, base_seconds * (2 ** max(0, attempt - 1)))


def fail_or_retry(db, guard, attempt, message, *, transient, max_attempts=3,
		base_seconds=30, now=None):
	"""Retry infrastructure failures only, with a capped number of attempts."""
	now = now or utcnow()
	message = str(message)[:500]
	update = {
		'$unset': {'inspection.claim_token': '', 'inspection.lease_until': ''},
	}
	if transient and attempt < max_attempts:
		update['$set'] = {
			'inspection.status': 'PENDING',
			'inspection.next_attempt_at': now + timedelta(
				seconds=retry_delay(attempt, base_seconds)),
			'inspection.error': message,
		}
		return 'PENDING', db.datasets.update_one(guard, update).modified_count == 1
	update['$set'] = {
		'inspection.status': 'FAILED',
		'inspection.finished_at': now,
		'inspection.error': message,
	}
	update['$unset']['inspection.next_attempt_at'] = ''
	return 'FAILED', db.datasets.update_one(guard, update).modified_count == 1


def recover_one_expired(db, *, max_attempts=3, base_seconds=30, now=None):
	"""Recover one orphaned lease; do not reclaim a live, unexpired claim."""
	now = now or utcnow()
	query = {
		'inspection.status': 'RUNNING',
		'inspection.lease_until': {'$lte': now},
		'inspection.claim_token': {'$type': 'string'},
	}
	doc = db.datasets.find_one(query, sort=[('inspection.lease_until', 1)])
	if doc is None:
		return False
	guard = claim_guard(doc, doc['inspection']['claim_token'])
	guard['inspection.lease_until'] = doc['inspection']['lease_until']
	attempt = doc['inspection'].get('attempt', max_attempts)
	fail_or_retry(db, guard, attempt, 'Inspection worker lease expired',
		transient=True, max_attempts=max_attempts,
		base_seconds=base_seconds, now=now)
	return True


def check_one_ready(db, validate_path, fingerprint, roots, *, check_interval_seconds=3600, now=None):
	"""Inspect one READY record for structural changes, without opening visibility arrays.

	Returns True only when a record was inspected (including a failed stat).
	This is a bounded, opportunistic cache-freshness check, not immutability proof.
	"""
	now = now or utcnow()
	cutoff = now - timedelta(seconds=check_interval_seconds)
	query = {
		'enabled': True,
		'inspection.status': 'READY',
		'inspection.source_fingerprint': {'$type': 'string'},
		'$or': [
			{'inspection.last_checked_at': {'$exists': False}},
			{'inspection.last_checked_at': {'$lte': cutoff}},
		],
	}
	doc = db.datasets.find_one(query, sort=[('inspection.last_checked_at', 1)])
	if doc is None:
		return False
	guard = {
		'_id': doc['_id'], 'enabled': True,
		'inspection.status': 'READY',
		'inspection.generation': doc['inspection']['generation'],
		'inspection.source_fingerprint': doc['inspection']['source_fingerprint'],
	}
	try:
		path = validate_path(doc, roots)
		current = fingerprint(path, doc['type'])
	except Exception:
		current = None
	if current == doc['inspection']['source_fingerprint']:
		db.datasets.update_one(guard, {'$set': {'inspection.last_checked_at': now}})
		return True
	# Reset rather than allowing a stale READY record to be returned.
	new_generation = uuid4().hex
	db.datasets.update_one(guard, {
		'$set': {
			'inspection.status': 'PENDING',
			'inspection.generation': new_generation,
			'inspection.attempt': 0,
			'inspection.requested_at': now,
		},
		'$unset': {
			'inspection.metadata': '', 'inspection.source_fingerprint': '',
			'inspection.inspector': '', 'inspection.schema': '',
			'inspection.finished_at': '', 'inspection.last_checked_at': '',
			'inspection.error': '', 'inspection.next_attempt_at': '',
			'inspection.claim_token': '', 'inspection.lease_until': '',
		},
	})
	return True
