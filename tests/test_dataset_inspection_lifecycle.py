"""Pure lifecycle tests; use stub for pymongo where not installed."""
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

try:
	import pymongo
except ImportError:
	stub = types.ModuleType('pymongo')
	stub.ReturnDocument = types.SimpleNamespace(AFTER='AFTER')
	sys.modules['pymongo'] = stub

from caesar_rest.dataset_inspection import lifecycle

NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


class LifecycleTests(unittest.TestCase):
	def test_claim_has_lease_and_atomic_token(self):
		db = MagicMock()
		db.datasets.find_one_and_update.return_value = {'dataset_id': 'a'}
		doc, token = lifecycle.claim_one(db, 'a', now=NOW, lease_seconds=100)
		self.assertEqual(doc['dataset_id'], 'a')
		self.assertEqual(len(token), 32)
		args, kwargs = db.datasets.find_one_and_update.call_args
		self.assertEqual(args[0]['dataset_id'], 'a')
		self.assertEqual(args[0]['inspection.attempt']['$lt'], 3)
		self.assertEqual(args[1]['$set']['inspection.lease_until'], NOW + timedelta(seconds=100))

	def test_retry_and_terminal_failure(self):
		db = MagicMock()
		db.datasets.update_one.return_value.modified_count = 1
		state, published = lifecycle.fail_or_retry(db, {'_id': 'x'}, 1, 'timeout', transient=True, now=NOW)
		self.assertEqual((state, published), ('PENDING', True))
		self.assertEqual(db.datasets.update_one.call_args.args[1]['$set']['inspection.next_attempt_at'], NOW + timedelta(seconds=30))
		state, published = lifecycle.fail_or_retry(db, {'_id': 'x'}, 3, 'timeout', transient=True, now=NOW)
		self.assertEqual((state, published), ('FAILED', True))
		state, published = lifecycle.fail_or_retry(db, {'_id': 'x'}, 1, 'invalid data', transient=False, now=NOW)
		self.assertEqual((state, published), ('FAILED', True))

	def test_recover_guards_existing_claim(self):
		db = MagicMock()
		lease = NOW - timedelta(seconds=1)
		db.datasets.find_one.return_value = {
			'_id': 8, 'inspection': {'generation': 'g', 'claim_token': 't',
				'lease_until': lease, 'attempt': 1},
		}
		db.datasets.update_one.return_value.modified_count = 1
		self.assertTrue(lifecycle.recover_one_expired(db, now=NOW))
		guard = db.datasets.update_one.call_args.args[0]
		self.assertEqual(guard['inspection.claim_token'], 't')
		self.assertEqual(guard['inspection.lease_until'], lease)
		self.assertEqual(guard['inspection.generation'], 'g')

	def test_ready_freshness_reset(self):
		db = MagicMock()
		db.datasets.find_one.return_value = {
			'_id': 8, 'type': 'file', 'inspection': {
				'status': 'READY', 'generation': 'old', 'source_fingerprint': 'oldfp'
			}
		}
		self.assertTrue(lifecycle.check_one_ready(db, lambda doc, roots: '/path',
			lambda path, kind: 'newfp', ['/'], now=NOW))
		update = db.datasets.update_one.call_args.args[1]
		self.assertEqual(update['$set']['inspection.status'], 'PENDING')
		self.assertNotEqual(update['$set']['inspection.generation'], 'old')
		self.assertIn('inspection.metadata', update['$unset'])


if __name__ == '__main__':
	unittest.main()
