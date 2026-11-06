
"""Controlled, idempotent bulk registration for Pipeline V2.

No scheduler submission. Individual registrations use the existing
single-run validation and authoritative artifact-binding mechanism.
"""

from caesar_rest.pipeline import bulk_planning
from caesar_rest.pipeline import idempotency
from caesar_rest.pipeline import manager


MAX_ITEMS = 32


def validate_request(payload):
	"""Validate the envelope before performing any registrations."""

	if (
		not isinstance(payload, dict)
		or set(payload) != {'items'}
	):
		raise manager.PipelineError(
			'Bulk registration requires an items array',
			400
		)

	items = payload['items']

	if (
		not isinstance(items, list)
		or not items
		or len(items) > MAX_ITEMS
	):
		raise manager.PipelineError(
			'items must contain 1-%d registrations' % MAX_ITEMS,
			400
		)

	seen_keys = set()
	seen_targets = set()

	for item in items:
		if (
			not isinstance(item, dict)
			or set(item) != {
				'idempotency_key',
				'registration'
			}
		):
			raise manager.PipelineError(
				'Each item requires idempotency_key and registration',
				400
			)

		key = idempotency.validate_key(
			item['idempotency_key']
		)

		registration = item['registration']

		if not isinstance(registration, dict):
			raise manager.PipelineError(
				'registration must be an object',
				400
			)

		stage = registration.get('stage')
		parameters = registration.get('parameters')
		node_id = registration.get('node_id')

		if (
			not isinstance(stage, str)
			or not stage
			or not isinstance(node_id, str)
			or not isinstance(parameters, dict)
			or not isinstance(parameters.get('target'), str)
			or not parameters['target']
		):
			raise manager.PipelineError(
				'Invalid bulk registration identity',
				400
			)

		manager.validate_identifier(node_id, 'node_id')

		identity = (stage, parameters['target'])

		if key in seen_keys:
			raise manager.PipelineError(
				'Duplicate idempotency key within bulk request',
				400
			)

		if identity in seen_targets:
			raise manager.PipelineError(
				'Duplicate stage and target within bulk request',
				400
			)

		seen_keys.add(key)
		seen_targets.add(identity)

	return items


def _existing(owner, pipeline_id, key, registration):
	"""Resolve completed registrations before checking current readiness."""

	_, runs, _ = manager.collections()

	return idempotency.find_existing(
		runs,
		owner,
		pipeline_id,
		key,
		idempotency.fingerprint(registration)
	)


def _current_proposal(owner, pipeline_id, registration):
	"""Verify a proposal against fresh application scientific readiness."""

	stage = registration['stage']
	target = registration['parameters']['target']

	plan = bulk_planning.plan(
		owner,
		pipeline_id,
		{
			'stage': stage,
			'targets': [target]
		}
	)

	items = plan.get('items')

	if not isinstance(items, list) or len(items) != 1:
		raise manager.PipelineError(
			'Scientific planner did not return one target',
			409
		)

	item = items[0]

	if item.get('can_register') is not True:
		raise manager.PipelineError(
			'Target is not currently plannable: %s' %
			','.join(
				item.get('blocking_reasons') or ['NOT_READY']
			),
			409
		)

	if item.get('registration') != registration:
		raise manager.PipelineError(
			'Registration proposal is stale or modified; '
			'request a fresh bulk plan',
			409
		)


def register(
	owner,
	pipeline_id,
	payload,
	retention_root='',
	max_directory_bytes=1024 * 1024 * 1024 * 1024,
	max_directory_entries=100000,
	max_directory_depth=16
):
	"""Register each item independently, preserving successful results."""

	items = validate_request(payload)

	# Authorize the pipeline before any replay lookup or registration.
	manager.get_pipeline(owner, pipeline_id)

	results = []

	for item in items:
		key = item['idempotency_key']
		registration = item['registration']

		try:
			# A committed registration always takes precedence over
			# newer selections, inspection refreshes and artifact state.
			existing = _existing(
				owner,
				pipeline_id,
				key,
				registration
			)

			if existing is not None:
				results.append({
					'idempotency_key': key,
					'status': 'REPLAYED',
					'run_id': existing['run_id'],
					'node_id': existing['node_id'],
					'run_status': existing['status']
				})
				continue

			_current_proposal(
				owner,
				pipeline_id,
				registration
			)

			# The existing single-run path performs all authoritative
			# pipeline, dataset and retained artifact checks.
			registration_payload = dict(registration)
			registration_payload['idempotency_key'] = key

			run = manager.create_run_simple(
				owner,
				pipeline_id,
				registration_payload,
				retention_root=retention_root,
				max_directory_bytes=max_directory_bytes,
				max_directory_entries=max_directory_entries,
				max_directory_depth=max_directory_depth
			)

			replayed = run.get('idempotency_replayed') is True

			results.append({
				'idempotency_key': key,
				'status': 'REPLAYED' if replayed else 'CREATED',
				'run_id': run['run_id'],
				'node_id': run['node_id'],
				'run_status': run['status']
			})

		except manager.PipelineError as exc:
			results.append({
				'idempotency_key': key,
				'status': 'FAILED',
				'http_status': exc.status,
				'error': str(exc)
			})

	created = sum(
		1 for item in results
		if item['status'] == 'CREATED'
	)

	replayed = sum(
		1 for item in results
		if item['status'] == 'REPLAYED'
	)

	failed = sum(
		1 for item in results
		if item['status'] == 'FAILED'
	)

	return {
		'schema': 'caesar.pipeline-bulk-registration.v1',
		'pipeline_id': pipeline_id,
		'summary': {
			'total': len(results),
			'created': created,
			'replayed': replayed,
			'failed': failed
		},
		'items': results
	}

