import tempfile
import unittest
from pathlib import Path
from caesar_rest.pipeline_submission_specs import create_specs, write_specs, PipelineSubmissionError

class SubmissionSpecsTests(unittest.TestCase):
	def specs(self, **overrides):
		kw = dict(workspace_app='/api/jobs/user/job_123', workspace_cluster='/cluster/jobs/user/job_123',
			inputfile='/api/data/obs.ms', cmd_arg_list=['--stage=GET_INFO', '--input-ms=/api/data/obs.ms'],
			image='/images/oxkat.sif', app_data_root='/api/data', cluster_data_root='/cluster/data',
			app_job_root='/api/jobs', cluster_job_root='/cluster/jobs')
		kw.update(overrides)
		return create_specs(**kw)

	def test_maps_source_and_removes_original_path(self):
		stage, exe = self.specs()
		self.assertEqual(stage['inputs'][0]['source'], '/cluster/data/obs.ms')
		self.assertEqual(exe['input_options'], {'input-ms': 'obs.ms'})
		self.assertEqual(exe['arguments'], ['--stage=GET_INFO'])
		self.assertNotIn('/api/data/obs.ms', repr(exe))

	def test_rejects_outside_roots(self):
		with self.assertRaises(PipelineSubmissionError):
			self.specs(inputfile='/secrets/obs.ms', cmd_arg_list=['--stage=GET_INFO', '--input-ms=/secrets/obs.ms'])

	def test_rejects_missing_input_option(self):
		with self.assertRaises(PipelineSubmissionError):
			self.specs(cmd_arg_list=['--stage=GET_INFO'])

	def test_rejects_duplicate_matches(self):
		with self.assertRaises(PipelineSubmissionError):
			self.specs(cmd_arg_list=['--stage=GET_INFO', '--input-ms=/api/data/obs.ms', '--other=/api/data/obs.ms'])

	def test_rejects_bad_workspace_mapping(self):
		with self.assertRaises(PipelineSubmissionError):
			self.specs(workspace_cluster='/cluster/jobs/user/elsewhere')

	def test_preserves_job_root_source(self):
		stage, _ = self.specs(inputfile='/api/jobs/user/previous/obs.ms',
			cmd_arg_list=['--stage=GET_INFO', '--input-ms=/api/jobs/user/previous/obs.ms'])
		self.assertEqual(stage['inputs'][0]['source'], '/cluster/jobs/user/previous/obs.ms')

	def test_exclusive_write(self):
		with tempfile.TemporaryDirectory() as td:
			stage, exe = self.specs()
			write_specs(td, stage, exe)
			self.assertTrue((Path(td) / 'execution_spec.json').is_file())
			with self.assertRaises(PipelineSubmissionError):
				write_specs(td, stage, exe)

if __name__ == '__main__':
	unittest.main()
