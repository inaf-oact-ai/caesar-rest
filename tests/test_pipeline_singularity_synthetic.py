import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from caesar_rest.pipeline_data_staging import stage_inputs, StagingError
from caesar_rest.pipeline_singularity_synthetic import (
	execute, singularity_synthetic_command
)


class SyntheticSingularityTests(unittest.TestCase):
	def prepare(self, root):
		image = root / 'image.sif'
		image.write_bytes(b'test image placeholder')
		src = root / 'source'
		src.mkdir()
		(src / 'image.fits').write_bytes(b'test fits\n')
		table = src / 'solutions.tbl'
		table.mkdir()
		(table / 'data').write_bytes(b'test table\n')
		ws = root / 'job'
		ws.mkdir()
		stage_inputs([
			{'source': str(src / 'image.fits'), 'name': 'image.fits', 'writable': False},
			{'source': str(table), 'name': 'solutions.tbl', 'writable': True},
		], str(ws))
		return ws, image

	def test_safe_argv_and_private_paths(self):
		with tempfile.TemporaryDirectory() as td:
			ws, image = self.prepare(Path(td))
			mock = Mock(return_value=Mock(returncode=0))
			self.assertEqual(execute(str(ws), str(image), '/mnt/job', mock), 0)
			args = mock.call_args.args[0]
			self.assertEqual(args[:5], ['singularity', 'exec', '--containall', '--no-home', '--bind'])
			self.assertEqual(args[5], str(ws) + ':/mnt/job:rw')
			self.assertIn('/mnt/job/input/image.fits', args)
			self.assertIn('/mnt/job/input/solutions.tbl', args)
			self.assertIn('/mnt/job/singularity_synthetic.json', args)
			self.assertTrue(mock.call_args.kwargs['check'] is False)

	def test_missing_ready_never_launches(self):
		with tempfile.TemporaryDirectory() as td:
			root = Path(td)
			ws = root / 'job'
			ws.mkdir()
			image = root / 'image.sif'
			image.write_bytes(b'x')
			mock = Mock()
			with self.assertRaises(StagingError):
				execute(str(ws), str(image), '/mnt/job', mock)
			mock.assert_not_called()

	def test_output_collision_never_launches(self):
		with tempfile.TemporaryDirectory() as td:
			ws, image = self.prepare(Path(td))
			(ws / 'singularity_synthetic.json').write_text('old')
			mock = Mock()
			with self.assertRaises(StagingError):
				execute(str(ws), str(image), '/mnt/job', mock)
			mock.assert_not_called()

	def test_missing_image_never_launches(self):
		with tempfile.TemporaryDirectory() as td:
			ws, image = self.prepare(Path(td))
			image.unlink()
			mock = Mock()
			with self.assertRaises(StagingError):
				execute(str(ws), str(image), '/mnt/job', mock)
			mock.assert_not_called()

	def test_unsafe_paths_rejected(self):
		with self.assertRaises(ValueError):
			singularity_synthetic_command('/jobs/../secret', '/image.sif', '/mnt/job', '/run.py')
		with self.assertRaises(ValueError):
			execute('/missing', '/image.sif', '/', Mock())

	def test_command_quoted(self):
		cmd = singularity_synthetic_command('/jobs/private job', '/opt/a.sif', '/mnt/job', '/opt/run.py')
		self.assertIn("'/jobs/private job'", cmd)
		self.assertIn('--container-workspace', cmd)


if __name__ == '__main__':
	unittest.main()
