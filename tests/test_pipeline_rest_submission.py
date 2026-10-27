"""Offline Flask-route regression tests for opt-in pipeline submission.

Requires the CAESAR-REST development environment; never calls Slurm or MongoDB.
"""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from flask import Flask

from caesar_rest import job_route


class PipelineRestSubmissionTests(unittest.TestCase):
	def setUp(self):
		self.app = Flask(__name__)
		self.app.secret_key = 'unit-test'
		self.app.config.update(
			JOB_SCHEDULER='slurm', MONGO_HOST='localhost', MONGO_PORT=27017,
			MONGO_DBNAME='test', DATASETS={}, JOB_DIR='/jobs',
			PIPELINE_STAGED_EXECUTION_ENABLED=True,
			PIPELINE_STAGED_APPLICATIONS=('oxkat',),
			DATASET_REGISTRY_ENABLED=True,
		)
		self.app.config['jobcfg'] = MagicMock()
		self.app.config['jobcfg'].validate.return_value = (
			'run_oxkat.sh', ['--stage=GET_INFO', '--input-ms=/data/obs.ms'],
			'', {'ncores': 1, 'nproc': 1})
		self.payload = {
			'app': 'oxkat', 'job_options': {'stage': 'GET_INFO'},
			'data_inputs': {'format': 'dataset', 'data': 'obs-id'},
			'pipeline_id': 'pipeline1', 'run_id': 'run1',
		}

	def invoke(self, overrides=None, submit_result=None, submit_error=None, claim_error=None):
		payload = dict(self.payload)
		if overrides:
			payload.update(overrides)
		with self.app.test_request_context('/caesar/api/v1.0/job', method='POST', json=payload):
			with ExitStack() as stack:
				stack.enter_context(patch.object(job_route.utils, 'get_storage_username', return_value='owner'))
				stack.enter_context(patch.object(job_route, 'process_data_inputs', return_value=(0, {}, '/data/obs.ms', 'obs-id')))
				claim = stack.enter_context(patch.object(job_route.pipeline_job_binding, 'claim_run', return_value=SimpleNamespace(owner='owner', run_id='run1')))
				if claim_error is not None:
					claim.side_effect = claim_error
				fail = stack.enter_context(patch.object(job_route, 'safe_fail_pipeline_submission'))
				finish = stack.enter_context(patch.object(job_route.pipeline_job_binding, 'finish_submission'))
				stack.enter_context(patch.object(job_route.pipeline_workspace, 'record_workspace', return_value=True))
				db = MagicMock()
				stack.enter_context(patch.object(job_route, 'mongo', SimpleNamespace(db=db)))
				submit = stack.enter_context(patch.object(job_route, 'submit_job_slurm'))
				if submit_error is not None:
					submit.side_effect = submit_error
				else:
					submit.return_value = submit_result
				response = job_route.submit_job.__wrapped__()
				return response.status_code, response.get_json(), claim, fail, finish, submit, db

	def test_success_records_staged_output_root_and_binding(self):
		result = {'job_id': 'j1', 'pid': 184, 'submit_date': '2026-10-19',
			'workspace': '/jobs/owner/job_j1', 'output_root': '/jobs/owner/job_j1/results'}
		status, body, claim, fail, finish, submit, db = self.invoke(submit_result=result)
		self.assertEqual(status, 202)
		self.assertEqual(body['job_id'], 'j1')
		self.assertEqual(claim.call_args.kwargs['dataset_id'], 'obs-id')
		self.assertTrue(claim.call_args.kwargs['require_dataset_binding'])
		self.assertEqual(submit.call_args.kwargs['staged_cmd_arg_list'][0], '--stage=GET_INFO')
		job_doc = db['owner.jobs'].insert.call_args.args[0]
		self.assertEqual(job_doc['output_root'], result['output_root'])
		self.assertEqual(job_doc['execution_mode'], 'staged_container')
		finish.assert_called_once()
		fail.assert_not_called()

	def test_pre_submission_failure_is_definite(self):
		status, _, _, fail, finish, _, _ = self.invoke(submit_error=job_route.SlurmPreSubmissionError('bad spec'))
		self.assertEqual(status, 400)
		self.assertFalse(fail.call_args.kwargs['uncertain'])
		finish.assert_not_called()

	def test_ambiguous_scheduler_reply_is_uncertain(self):
		status, _, _, fail, finish, _, _ = self.invoke(submit_result=None)
		self.assertEqual(status, 500)
		self.assertTrue(fail.call_args.kwargs['uncertain'])
		finish.assert_not_called()

	def test_unexpected_scheduler_exception_is_uncertain(self):
		status, _, _, fail, _, _, _ = self.invoke(submit_error=RuntimeError('timeout'))
		self.assertEqual(status, 500)
		self.assertTrue(fail.call_args.kwargs['uncertain'])

	def test_unsupported_application_rejected_before_claim(self):
		status, _, claim, fail, _, submit, _ = self.invoke(overrides={'app': 'fextractor'})
		self.assertEqual(status, 400)
		claim.assert_not_called()
		submit.assert_not_called()
		fail.assert_not_called()

	def test_non_dataset_input_rejected_before_claim(self):
		status, _, claim, _, _, submit, _ = self.invoke(overrides={
			'data_inputs': {'format': 'abspath', 'data': '/data/obs.ms'}})
		self.assertEqual(status, 400)
		claim.assert_not_called()
		submit.assert_not_called()

	def test_dataset_mismatch_from_claim_is_409(self):
		err = job_route.pipeline_job_binding.manager.PipelineError('Dataset mismatch', 409)
		status, _, claim, fail, finish, submit, _ = self.invoke(claim_error=err)
		self.assertEqual(status, 409)
		claim.assert_called_once()
		fail.assert_not_called()
		finish.assert_not_called()
		submit.assert_not_called()


if __name__ == '__main__':
	unittest.main()
