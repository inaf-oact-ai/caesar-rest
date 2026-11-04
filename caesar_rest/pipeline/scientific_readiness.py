
"""Generic dispatcher for application-specific scientific readiness.

Provider methods receive authorized dataset and pipeline metadata.
No scheduler activity, filesystem access, or database modifications.
"""

from caesar_rest.pipeline import manager


def resolve_snapshot(pipeline, runs, dataset_doc, provider):
	"""Dispatch to the application's scientific readiness provider."""

	if not isinstance(pipeline, dict):
		raise manager.PipelineError(
			'Invalid pipeline metadata', 409
		)

	if not isinstance(dataset_doc, dict):
		raise manager.PipelineError(
			'Invalid dataset metadata', 409
		)

	if pipeline.get('dataset_id') != dataset_doc.get('dataset_id'):
		raise manager.PipelineError(
			'Pipeline dataset association mismatch', 409
		)

	method = getattr(provider, 'build_scientific_readiness', None)

	if not callable(method):
		raise manager.PipelineError(
			'Application has no scientific readiness provider', 409
		)

	result = method(pipeline, runs, dataset_doc)

	if not isinstance(result, dict):
		raise manager.PipelineError(
			'Invalid scientific readiness provider response', 500
		)

	return {
		'schema': 'caesar.pipeline-scientific-readiness.v1',
		'pipeline_id': pipeline.get('pipeline_id'),
		'dataset_id': pipeline.get('dataset_id'),
		'application': manager.get_pipeline_app(pipeline),
		'scientific': result
	}


def resolve(owner, pipeline_id):
	"""Resolve scientific readiness using authorized persisted metadata."""

	from caesar_rest import dataset_registry
	from caesar_rest.job_configurator import JobConfigurator

	pipeline = manager.get_pipeline(owner, pipeline_id)
	dataset_id = pipeline.get('dataset_id')

	if not isinstance(dataset_id, str) or not dataset_id:
		raise manager.PipelineError(
			'Pipeline has no registered dataset association', 409
		)

	try:
		dataset_doc = dataset_registry.get_dataset(dataset_id)
	except dataset_registry.DatasetError as exc:
		raise manager.PipelineError(str(exc), exc.status)

	app = manager.get_pipeline_app(pipeline)

	configurators = JobConfigurator().app_configurators
	configurator_class = configurators.get(app)

	if configurator_class is None:
		raise manager.PipelineError(
			'Application has no registered configurator', 409
		)

	provider = configurator_class(app_name=app)

	_, runs_collection, _ = manager.collections()

	runs = list(runs_collection.find({
		'owner': owner,
		'pipeline_id': pipeline_id
	}))

	return resolve_snapshot(
		pipeline,
		runs,
		dataset_doc,
		provider
	)

