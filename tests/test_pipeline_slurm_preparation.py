import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from caesar_rest.pipeline_stage_runner import prepare, main
from caesar_rest.pipeline_data_staging import StagingError
from caesar_rest.pipeline_slurm_preparation import preparation_script


class PreparationTests(unittest.TestCase):
	def test_multiple_inputs(self):
		with tempfile.TemporaryDirectory() as td:
			root = Path(td)
			src1 = root / 'image.fits'
			src1.write_bytes(b'fits')
			src2 = root / 'solutions.tbl'
			src2.mkdir()
			(src2 / 'data').write_bytes(b'table')
			workspace = root / 'job_123'
			workspace.mkdir()
			spec = workspace / 'staging_spec.json'
			spec.write_text(json.dumps({'version': 1, 'inputs': [
				{'source': str(src1), 'name': 'image.fits', 'writable': False},
				{'source': str(src2), 'name': 'solutions.tbl', 'writable': True}
			]}))
			manifest = prepare(str(spec), str(workspace))
			self.assertEqual(manifest['staging_state'], 'READY')
			self.assertEqual(len(manifest['inputs']), 2)
			self.assertEqual((workspace / 'input' / 'staging.json').exists(), True)
			(workspace / 'input' / 'solutions.tbl' / 'data').write_bytes(b'changed')
			self.assertEqual((src2 / 'data').read_bytes(), b'table')

	def test_failed_source_does_not_publish_ready(self):
		with tempfile.TemporaryDirectory() as td:
			root = Path(td)
			workspace = root / 'job'
			workspace.mkdir()
			spec = workspace / 'staging_spec.json'
			spec.write_text(json.dumps({'version': 1, 'inputs': [{'source': str(root / 'missing.fits')}] }))
			self.assertEqual(main(['--spec', str(spec), '--workspace', str(workspace)]), 1)
			self.assertFalse((workspace / 'input' / 'staging.json').exists())

	def test_reject_external_spec(self):
		with tempfile.TemporaryDirectory() as td:
			root = Path(td)
			workspace = root / 'job'
			workspace.mkdir()
			spec = root / 'outside.json'
			spec.write_text('{}')
			with self.assertRaises(StagingError):
				prepare(str(spec), str(workspace))

	def test_script_is_prepare_only_and_shell_quoted(self):
		script = preparation_script('/jobs/job 1/staging_spec.json', '/jobs/job 1', '/opt/staging/runner.py')
		self.assertIn('set -e', script)
		self.assertIn("'/jobs/job 1'", script)
		self.assertNotIn('singularity', script)

	def test_reject_spec_other_workspace(self):
		with self.assertRaises(ValueError):
			preparation_script('/tmp/foreign.json', '/jobs/job1', '/opt/staging/runner.py')


if __name__ == '__main__':
	unittest.main()

class SlurmPayloadTests(unittest.TestCase):
	def test_existing_slurm_contract(self):
		from unittest.mock import Mock
		from caesar_rest.pipeline_slurm_preparation import build_preparation_job
		mgr = Mock()
		mgr.check_submit_vars.return_value = 0
		mgr.cluster_batch_workdir = '/cluster/batchlogs'
		body = json.loads(build_preparation_job(mgr, 'test_123',
			'/jobs/job_123/staging_spec.json', '/jobs/job_123', '/opt/stage.py'))
		self.assertEqual(body['job']['name'], 'test_123')
		self.assertEqual(body['job']['current_working_directory'], '/cluster/batchlogs')
		self.assertIn('set -e', body['script'])
		self.assertNotIn('singularity', body['script'])
