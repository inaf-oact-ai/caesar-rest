"""Runtime dependency checks for optional execution backends.

The Celery task modules are intentionally imported lazily: importing REST
routes must not register or require Celery tasks on a Slurm installation.
"""


def require_celery_app():
	"""Return the configured Celery instance or raise an actionable error."""
	from caesar_rest import celery
	if celery is None:
		raise RuntimeError(
			"Celery backend is unavailable. Install the Celery optional "
			"dependencies and restart CAESAR-REST before selecting "
			"--job_scheduler=celery."
		)
	return celery


def require_background_task():
	"""Load the legacy worker task only when a Celery API is invoked."""
	require_celery_app()
	from caesar_rest.workers import background_task
	return background_task
