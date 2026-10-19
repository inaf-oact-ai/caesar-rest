import json
import tempfile
import unittest
from pathlib import Path

from caesar_rest.pipeline_data_staging import StagingError, stage_inputs
from caesar_rest.pipeline_synthetic_execution import consume, main, synthetic_execution_command


class SyntheticExecutionTests(unittest.TestCase):
	def fixture(self, base):
		image = base / 'image.fits'
		image.write_bytes(b'test fits\n')
		solutions = base / 'solutions.tbl'
		solutions.mkdir()
		(solutions / 'data').write_bytes(b'test table\n')
		workspace = base / 'job'
		workspace.mkdir()
		return image, solutions, workspace

	def test_prepare_resolve_execute_does_not_change_origins(self):
		with tempfile.TemporaryDirectory() as td:
			image, solutions, workspace = self.fixture(Path(td))
			stage_inputs([
				{'source': str(image), 'name': 'image.fits', 'writable': False},
				{'source': str(solutions), 'name': 'solutions.tbl', 'writable': True}
			], str(workspace))
			out = consume(str(workspace))
			self.assertEqual(json.loads(out.read_text())['status'], 'EXECUTED')
			self.assertEqual((solutions / 'data').read_bytes(), b'test table\n')
			self.assertEqual(image.read_bytes(), b'test fits\n')
			self.assertEqual((workspace / 'input' / 'solutions.tbl' / 'data').read_bytes(), b'synthetic execution changed private table\n')

	def test_missing_manifest_fails_closed(self):
		with tempfile.TemporaryDirectory() as td:
			_, _, workspace = self.fixture(Path(td))
			self.assertEqual(main(['--workspace', str(workspace)]), 1)
			self.assertFalse((workspace / 'synthetic_execution.json').exists())

	def test_missing_expected_input_fails_closed(self):
		with tempfile.TemporaryDirectory() as td:
			image, _, workspace = self.fixture(Path(td))
			stage_inputs([{'source': str(image), 'name': 'image.fits', 'writable': False}], str(workspace))
			with self.assertRaises(StagingError):
				consume(str(workspace))

	def test_reexecution_refuses_overwrite(self):
		with tempfile.TemporaryDirectory() as td:
			image, solutions, workspace = self.fixture(Path(td))
			stage_inputs([
				{'source': str(image), 'name': 'image.fits', 'writable': False},
				{'source': str(solutions), 'name': 'solutions.tbl', 'writable': True}
			], str(workspace))
			consume(str(workspace))
			with self.assertRaises(StagingError):
				consume(str(workspace))

	def test_command_is_quoted_and_fixed(self):
		command = synthetic_execution_command('/storage/jobs/a job', '/opt/src/consumer.py', '/usr/bin/python3')
		self.assertIn("'/storage/jobs/a job'", command)
		self.assertIn('/opt/src/consumer.py', command)
		with self.assertRaises(ValueError):
			synthetic_execution_command('/tmp/job\nexit 0', '/opt/src/consumer.py')


if __name__ == '__main__':
	unittest.main()
