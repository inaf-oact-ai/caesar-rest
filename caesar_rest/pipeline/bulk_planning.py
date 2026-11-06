
"""Generic, read-only bulk planning for scientific pipelines.

Application providers translate scientific readiness into registration
proposals. No runs are registered and no jobs are submitted here.
"""

from caesar_rest.pipeline import manager
from caesar_rest.pipeline import scientific_readiness


MAX_TARGETS = 128


def validate_request(payload):
	"""Validate application-independent bulk planning parameters."""

	if not isinstance(payload, dict):
		raise manager.PipelineError(
			'Expected a JSON object', 400
		)

	if set(payload) - {'stage', 'targets'}:
		raise manager.PipelineError(
			'Unsupported bulk planning field', 400
		)

	stage = payload.get('stage')

	if not isinstance(stage, str) or not stage:
		raise manager.PipelineError(
			'stage must be a nonempty string', 400
		)

	targets = payload.get('targets')

	if targets is not None:
		if (
			not isinstance(targets, list)
			or not targets
			or len(targets) > MAX_TARGETS
		):
			raise manager.PipelineError(
				'targets must be a nonempty list with at most '
				'%d elements' % MAX_TARGETS,
				400
			)

		for target in targets:
			if not isinstance(target, str) or not target:
				raise manager.PipelineError(
					'Invalid target identity', 400
				)

		if len(set(targets)) != len(targets):
			raise manager.PipelineError(
				'Duplicate target identity', 400
			)

	return stage, targets


def plan_snapshot(scientific_snapshot, stage, targets, provider):
	"""Ask an application provider to prepare registration proposals."""

	if not isinstance(scientific_snapshot, dict):
		raise manager.PipelineError(
			'Invalid scientific readiness snapshot', 500
		)

	method = getattr(provider, 'build_bulk_plan', None)

	if not callable(method):
		raise manager.PipelineError(
			'Application does not support bulk planning', 409
		)

	result = method(
		scientific_snapshot.get('scientific'),
		stage,
		targets
	)

	if not isinstance(result, dict):
		raise manager.PipelineError(
			'Invalid bulk planning provider response', 500
		)

	items = result.get('items')

	if not isinstance(items, list):
		raise manager.PipelineError(
			'Invalid bulk planning items', 500
		)

	return {
		'schema': 'caesar.pipeline-bulk-plan.v1',
		'pipeline_id': scientific_snapshot.get('pipeline_id'),
		'dataset_id': scientific_snapshot.get('dataset_id'),
		'application': scientific_snapshot.get('application'),
		'stage': stage,
		'status': result.get('status'),
		'summary': {
			'total': len(items),
			'plannable': sum(
				1 for item in items
				if item.get('can_register') is True
			),
			'blocked': sum(
				1 for item in items
				if item.get('can_register') is not True
			)
		},
		'items': items
	}


def plan(owner, pipeline_id, payload):
	"""Build a fresh plan without modifying persisted pipeline state."""

	from caesar_rest.job_configurator import JobConfigurator

	stage, targets = validate_request(payload)

	# Includes owner-scoped pipeline access, dataset authorization,
	# inspection metadata and current selected-run readiness.
	snapshot = scientific_readiness.resolve(
		owner,
		pipeline_id
	)

	app = snapshot['application']

	# Verify that the requested stage is enabled by the server's
	# current Pipeline V2 application policy.
	manager.validate_pipeline_stage(app, stage)

	configurator_class = JobConfigurator().app_configurators.get(app)

	if configurator_class is None:
		raise manager.PipelineError(
			'Application has no registered configurator', 409
		)

	provider = configurator_class(app_name=app)

	return plan_snapshot(
		snapshot,
		stage,
		targets,
		provider
	)

