"""Run with python -m unittest tests.test_m1dc3_slurm_hook -v after copying into tests/."""
import json
import subprocess
import unittest
from caesar_rest.slurm_client import SlurmJobManager


class SlurmPreparationHookTests(unittest.TestCase):
	def make_manager(self):
		m = SlurmJobManager()
		m.username = 'caesar'
		m.cluster_queue = 'test'
		m.cluster_batch_workdir = '/opt/slurm/batchlogs/caesar-rest'
		m.cluster_jobdir = m.app_jobdir = '/storage/jobs'
		m.cluster_datadir = m.app_datadir = '/storage/data'
		m.cluster_modeldir = m.app_modeldir = '/storage/models'
		m.sleep_before_run = False
		return m

	def make_job(self, preparation=None):
		return self.make_manager().create_job(
			image='/opt/images/science.sif', job_args='--stage=GET_INFO',
			inputfile='/storage/data/input.ms', job_name='testjob',
			job_outdir='/storage/jobs/owner/job_test', preparation=preparation)

	def prep(self, **updates):
		p = {
			'mode': 'prepare_only',
			'workspace': '/storage/jobs/owner/job_test',
			'spec_path': '/storage/jobs/owner/job_test/staging_spec.json',
			'runner_path': '/opt/src/pipeline_runtime/stage_runner.py',
			'python_executable': '/usr/bin/python3',
		}
		p.update(updates)
		return p

	def test_legacy_script_unchanged(self):
		obj = json.loads(self.make_job())
		self.assertIn('singularity run', obj['script'])
		self.assertNotIn('pipeline_stage_runner', obj['script'])

	def test_prepare_only_script(self):
		obj = json.loads(self.make_job(self.prep()))
		script = obj['script']
		self.assertIn('set -e', script)
		self.assertIn('/opt/src/pipeline_runtime/stage_runner.py', script)
		self.assertNotIn('singularity run', script)
		self.assertEqual(subprocess.run(['bash', '-n'], input=script, text=True, capture_output=True).returncode, 0)

	def test_reject_execute_until_staged_paths_supported(self):
		self.assertIsNone(
			self.make_job(
				self.prep(mode='prepare_then_execute')
			)
		)	

	def test_reject_mismatched_workspace(self):
		self.assertIsNone(
			self.make_job(
				self.prep(workspace='/storage/jobs/another/job_test')
			)
		)

	def test_reject_spec_outside_workspace(self):
		self.assertIsNone(
			self.make_job(
				self.prep(spec_path='/tmp/untrusted.json')
			)
		)


if __name__ == '__main__':
	unittest.main()
