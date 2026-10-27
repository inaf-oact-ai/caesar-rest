
import pytest

from flask import Flask

from caesar_rest import job_route


@pytest.fixture
def app():
	app = Flask(__name__)

	# - Populate image configuration with identifiable test values.
	for name, spec in job_route.JOB_APPLICATIONS.items():

		if name == 'fextractor':
			for variant, keys in spec['variants'].items():
				for key in keys:
					app.config[key] = 'test-image:' + key

		else:
			kube_key, _ = spec['kubernetes']

			app.config[kube_key] = 'test-image:' + kube_key
			app.config[spec['slurm']] = (
				'test-image:' + spec['slurm']
			)

	return app


@pytest.mark.parametrize(
	'scheduler',
	['kubernetes', 'slurm']
)
def test_all_registered_apps_resolve(app, scheduler):
	with app.app_context():

		for app_name in job_route.JOB_APPLICATIONS:

			run_opts = (
				{'container_variant': 'torch'}
				if app_name == 'fextractor'
				else {}
			)

			result = job_route.resolve_job_application(
				app_name,
				scheduler,
				run_opts
			)

			assert result['image'].startswith('test-image:')
			assert 'app_mode' in result

			if scheduler == 'kubernetes':
				assert result['job_label']


@pytest.mark.parametrize(
	'variant',
	['tf', 'torch', 'chronos', 'moirai', 'fats', 'licu', 'falcon']
)
@pytest.mark.parametrize(
	'scheduler',
	['kubernetes', 'slurm']
)
def test_fextractor_variants(app, scheduler, variant):
	with app.app_context():

		result = job_route.resolve_job_application(
			'fextractor',
			scheduler,
			{'container_variant': variant}
		)

		assert variant.upper() in result['image']


@pytest.mark.parametrize(
	'app_name,expected_mode',
	[
		('classifier-vit', 'image'),
		('classifier-vit-catalog', 'catalog'),
		('oxkat', ''),
	]
)
@pytest.mark.parametrize(
	'scheduler',
	['kubernetes', 'slurm']
)
def test_application_modes(
	app,
	scheduler,
	app_name,
	expected_mode
):
	with app.app_context():

		result = job_route.resolve_job_application(
			app_name,
			scheduler,
			{}
		)

		assert result['app_mode'] == expected_mode


def test_unknown_application_rejected(app):
	with app.app_context():

		with pytest.raises(
			job_route.JobApplicationConfigError
		):
			job_route.resolve_job_application(
				'unknown-application',
				'slurm',
				{}
			)


def test_unknown_fextractor_variant_rejected(app):
	with app.app_context():

		with pytest.raises(
			job_route.JobApplicationConfigError
		):
			job_route.resolve_job_application(
				'fextractor',
				'slurm',
				{'container_variant': 'unknown'}
			)


def test_missing_configuration_is_not_silently_ignored():
	app = Flask(__name__)

	with app.app_context():

		with pytest.raises(KeyError):
			job_route.resolve_job_application(
				'oxkat',
				'slurm',
				{}
			)

