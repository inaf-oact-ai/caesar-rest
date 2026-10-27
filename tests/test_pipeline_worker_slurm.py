import unittest
from caesar_rest.pipeline.submission.worker_slurm import worker_commands


class WorkerCommandsTests(unittest.TestCase):
	def test_worker_commands(self):
		workspace = '/cluster/jobs/u/job_1'
		digest = 'a' * 64
		check, prepare, execute = worker_commands(workspace, workspace + '/staging_spec.json', workspace + '/execution_spec.json', workspace + '/caesar-pipeline-worker.pyz', digest)
		self.assertIn('sha256sum -c --status', check)
		self.assertIn(' prepare ', prepare)
		self.assertIn(' execute ', execute)
		self.assertIn('staging_spec.json', prepare)
		self.assertIn('execution_spec.json', execute)

	def test_bad_location_fails_closed(self):
		ws = '/cluster/jobs/u/job_1'
		with self.assertRaises(ValueError):
			worker_commands(ws, ws + '/staging_spec.json', ws + '/execution_spec.json', '/tmp/worker.pyz', 'a'*64)

if __name__ == '__main__':
	unittest.main()
