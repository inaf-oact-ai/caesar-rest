
#!/usr/bin/env python3
"""One-off local administrator command for retained Pipeline V2 reconciliation.

Defaults to a read-only plan. Requires --apply for copies and MongoDB update.
Run from the CAESAR-REST virtualenv with CAESAR_REST_DB* environment set.
"""

import argparse
import json
import os
import sys

from pymongo import MongoClient

from caesar_rest.pipeline.artifacts.reconciliation import reconcile_retained_run


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('--pipeline-id', required=True)
	parser.add_argument('--node-id', required=True)
	parser.add_argument('--run-id', required=True)
	parser.add_argument('--retention-root', required=True)
	parser.add_argument('--apply', action='store_true', help='Actually copy and publish missing artifacts')
	parser.add_argument('--db-name', default=os.environ.get('CAESAR_REST_DBNAME'))
	parser.add_argument('--db-host', default=os.environ.get('CAESAR_REST_DBHOST', 'localhost'))
	parser.add_argument('--db-port', type=int, default=int(os.environ.get('CAESAR_REST_DBPORT', '27017')))
	args = parser.parse_args()
	if not args.db_name:
		parser.error('Database name missing: set CAESAR_REST_DBNAME or --db-name')

	client = MongoClient(args.db_host, args.db_port, serverSelectionTimeoutMS=10000)
	try:
		db = client[args.db_name]
		identity = {
			'pipeline_id': args.pipeline_id,
			'node_id': args.node_id,
			'run_id': args.run_id,
		}
		run = db.pipeline_runs.find_one(identity, {'owner': 1})
		if run is None or not run.get('owner'):
			raise RuntimeError('Run not found or owner missing')
		result = reconcile_retained_run(
			db, run['owner'], args.pipeline_id, args.node_id,
			args.run_id, args.retention_root, dry_run=not args.apply
		)
		print(json.dumps(result, indent=2, sort_keys=True))
	finally:
		client.close()


if __name__ == '__main__':
	try:
		main()
	except Exception as exc:
		print('Reconciliation failed: %s' % exc, file=sys.stderr)
		raise SystemExit(1)

