import json
import subprocess
import unittest

from caesar_rest.slurm_client import SlurmJobManager


class SyntheticSlurmHookTests(unittest.TestCase):
	def manager(self):
		m = SlurmJobManager()
		m.username = 'caesar'
		m.cluster_queue = 'test'
		m.cluster_batch_workdir = '/opt/slurm/batchlogs/caesar-rest'
		m.cluster_jobdir = m.app_jobdir = '/storage/jobs'
		m.cluster_datadir = m.app_datadir = '/storage/data'
		m.cluster_modeldir = m.app_modeldir = '/storage/models'
		m.sleep_before_run = False
		return m

	def create(self, preparation=None):
		return self.manager().create_job(
			image='/opt/images/science.sif', job_args='--stage=GET_INFO',
			inputfile='/storage/data/input.ms', job_name='testjob',
			job_outdir='/storage/jobs/owner/job_test', preparation=preparation)

	def preparation(self, mode):
		return {
			'mode': mode,
			'workspace': '/storage/jobs/owner/job_test',
			'spec_path': '/storage/jobs/owner/job_test/staging_spec.json',
			'runner_path': '/opt/src/pipeline_runtime/stage_runner.py',
			'execution_runner_path': '/opt/src/caesar_rest/pipeline/execution/synthetic.py',
			'python_executable': '/usr/bin/python3',
		}

	def test_preparation_then_synthetic_execution(self):
		result = self.create(self.preparation('prepare_then_execute_synthetic'))
		self.assertIsNotNone(result)
		script = json.loads(result)['script']
		self.assertIn('set -e', script)
		self.assertIn('/opt/src/pipeline_runtime/stage_runner.py', script)
		self.assertIn('/opt/src/caesar_rest/pipeline/execution/synthetic.py', script)
		self.assertLess(
			script.index('/opt/src/pipeline_runtime/stage_runner.py'),
			script.index('/opt/src/caesar_rest/pipeline/execution/synthetic.py')
		)
		self.assertNotIn('singularity run', script)
		self.assertEqual(subprocess.run(['bash', '-n'], input=script, text=True, capture_output=True).returncode, 0)

	def test_unrestricted_execute_still_rejected(self):
		self.assertIsNone(self.create(self.preparation('prepare_then_execute')))

	def test_synthetic_mode_requires_execution_runner(self):
		p = self.preparation('prepare_then_execute_synthetic')
		del p['execution_runner_path']
		self.assertIsNone(self.create(p))

	def test_prepare_only_stays_prepare_only(self):
		result = self.create(self.preparation('prepare_only'))
		self.assertIsNotNone(result)
		script = json.loads(result)['script']
		self.assertNotIn('/opt/src/caesar_rest/pipeline/execution/synthetic.py', script)


if __name__ == '__main__':
	unittest.main()
