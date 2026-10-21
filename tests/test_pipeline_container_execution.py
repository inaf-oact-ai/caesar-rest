import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from pipeline_runtime.executor import execute, execution_command, ContainerExecutionError


class ContainerExecutionTests(unittest.TestCase):
	def setUp(self):
		self.temp = tempfile.TemporaryDirectory()
		self.addCleanup(self.temp.cleanup)
		self.ws = Path(self.temp.name) / 'job_001'
		self.ws.mkdir()
		(self.ws / 'input').mkdir()
		(self.ws / 'input' / 'sample.ms').mkdir()
		self.image = Path(self.temp.name) / 'app.sif'
		self.image.write_bytes(b'image')
		self.spec = self.ws / 'execution_spec.json'
		self.payload = {'version': 1, 'image': str(self.image), 'container_workspace': '/mnt/job',
			'arguments': ['--stage=GET_INFO'], 'input_options': {'input-ms': 'sample.ms'},
			'execution_dir': 'execution', 'output_dir': 'results'}

	def write(self):
		self.spec.write_text(json.dumps(self.payload))

	def test_success_uses_normal_image_entrypoint_and_private_input(self):
		self.write()
		calls = []
		def run(argv, check):
			calls.append(argv)
			return SimpleNamespace(returncode=0)
		
		with patch(
			'pipeline_runtime.executor.resolve_staged_inputs',
			return_value=(
				{'sample.ms': str(self.ws / 'input' / 'sample.ms')},
				{}
			)
		):
			self.assertEqual(execute(str(self.ws), str(self.spec), runner=run), 0)
			
		argv = calls[0]
		self.assertEqual(argv[:2], ['singularity', 'run'])
		self.assertEqual(argv[-1], str(self.image))
		self.assertIn('JOB_OPTIONS=--stage=GET_INFO --input-ms=/mnt/job/input/sample.ms', argv)
		self.assertIn('JOB_DIR=/mnt/job/execution', argv)
		self.assertIn('JOB_OUTDIR=/mnt/job/results', argv)
		self.assertNotIn(str(self.ws / 'input' / 'sample.ms'), ' '.join(argv))

	def test_reject_existing_input_option(self):
		self.payload['arguments'].append('--input-ms=/original.ms')
		self.write()
		with patch(
			'pipeline_runtime.executor.resolve_staged_inputs',
			return_value=(
				{'sample.ms': str(self.ws / 'input' / 'sample.ms')},
				{}
			)
		):
			with self.assertRaises(ContainerExecutionError):
				execute(str(self.ws), str(self.spec))

	def test_reject_reuse(self):
		self.write()
		(self.ws / 'execution').mkdir()
		with patch(
			'pipeline_runtime.executor.resolve_staged_inputs',
			return_value=(
				{'sample.ms': str(self.ws / 'input' / 'sample.ms')},
				{}
			)
		):
			with self.assertRaises(ContainerExecutionError):
				execute(str(self.ws), str(self.spec))

	def test_reject_outside_workspace_spec(self):
		self.assertRaises(ContainerExecutionError, execution_command, str(self.ws), str(self.image), '/runner.py')

	def test_no_client_command_override(self):
		self.payload['arguments'] = ['--stage=GET_INFO', '--cmd=$(whoami)']
		self.write()
		with self.assertRaises(ContainerExecutionError):
			execute(str(self.ws), str(self.spec))


if __name__ == '__main__':
	unittest.main()
