import json
import subprocess
import unittest

from caesar_rest.slurm_client import SlurmJobManager


class ContainerSlurmHookTests(unittest.TestCase):
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

	def preparation(self):
		return {
			'mode': 'prepare_then_execute_container',
			'workspace': '/storage/jobs/owner/job_test',
			'spec_path': '/storage/jobs/owner/job_test/staging_spec.json',
			'runner_path': '/opt/src/caesar_rest/pipeline_stage_runner.py',
			'execution_spec_path': '/storage/jobs/owner/job_test/execution_spec.json',
			'container_execution_runner_path': '/opt/src/caesar_rest/pipeline_container_execution.py',
			'python_executable': '/usr/bin/python3',
		}

	def create(self, p=None):
		return self.manager().create_job(
			image='/opt/images/science.sif',
			job_args='--stage=GET_INFO',
			inputfile='/storage/data/input.ms',
			job_name='testjob',
			job_outdir='/storage/jobs/owner/job_test',
			preparation=p,
		)

	def test_two_commands_in_one_fail_closed_script(self):
		body = self.create(self.preparation())
		self.assertIsNotNone(body)
		script = json.loads(body)['script']
		self.assertTrue(script.startswith('#!/bin/bash\nset -e\n'))
		self.assertEqual(script.count('pipeline_stage_runner.py'), 1)
		self.assertEqual(script.count('pipeline_container_execution.py'), 1)
		self.assertLess(script.index('pipeline_stage_runner.py'), script.index('pipeline_container_execution.py'))
		self.assertNotIn('singularity run', script)
		self.assertEqual(subprocess.run(['bash', '-n'], input=script, text=True, capture_output=True).returncode, 0)

	def test_missing_execution_spec_rejected(self):
		p = self.preparation()
		del p['execution_spec_path']
		self.assertIsNone(self.create(p))

	def test_missing_runner_rejected(self):
		p = self.preparation()
		del p['container_execution_runner_path']
		self.assertIsNone(self.create(p))

	def test_execution_spec_outside_workspace_rejected(self):
		p = self.preparation()
		p['execution_spec_path'] = '/storage/jobs/other/execution_spec.json'
		self.assertIsNone(self.create(p))

	def test_legacy_job_still_uses_original_script(self):
		body = self.create(None)
		self.assertIsNotNone(body)
		script = json.loads(body)['script']
		self.assertIn('singularity run', script)
		self.assertNotIn('pipeline_container_execution.py', script)

	def test_old_prepare_only_unaffected(self):
		p = self.preparation()
		p['mode'] = 'prepare_only'
		body = self.create(p)
		self.assertIsNotNone(body)
		script = json.loads(body)['script']
		self.assertNotIn('pipeline_container_execution.py', script)


if __name__ == '__main__':
	unittest.main()
