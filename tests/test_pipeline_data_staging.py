import json
import tempfile
import unittest
from pathlib import Path

from caesar_rest.pipeline_data_staging import stage_input, StagingError
from caesar_rest.pipeline_ms_staging import stage_ms


class StageTests(unittest.TestCase):
	def test_ms_compatibility_and_independence(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			src = base / 'observation.ms'
			src.mkdir()
			(src / 'table.dat').write_bytes(b'original')
			workspace = base / 'job_123'
			workspace.mkdir()
			result = stage_ms(str(src), str(workspace))
			private = Path(result['private_ms'])
			private.joinpath('table.dat').write_bytes(b'changed')
			self.assertEqual(src.joinpath('table.dat').read_bytes(), b'original')
			self.assertEqual(json.loads((workspace / 'input' / 'staging.json').read_text())['staging_state'], 'READY')
			with self.assertRaises(StagingError):
				stage_ms(str(src), str(workspace))

	def test_generic_file(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			src = base / 'image.fits'
			src.write_bytes(b'fits')
			workspace = base / 'job'
			workspace.mkdir()
			result = stage_input(str(src), str(workspace), writable=True)
			self.assertEqual(result['input_type'], 'file')
			Path(result['private_path']).write_bytes(b'changed')
			self.assertEqual(src.read_bytes(), b'fits')

	def test_generic_directory(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			src = base / 'calibration'
			src.mkdir()
			(src / 'solutions.tbl').write_bytes(b'original')
			workspace = base / 'job'
			workspace.mkdir()
			result = stage_input(str(src), str(workspace), writable=True)
			self.assertEqual(Path(result['private_path'], 'solutions.tbl').read_bytes(), b'original')

	def test_reject_symlink_and_unsafe_name(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			src = base / 'observation.ms'
			src.mkdir()
			(src / 'linked').symlink_to('/tmp')
			workspace = base / 'job'
			workspace.mkdir()
			with self.assertRaises(StagingError):
				stage_ms(str(src), str(workspace))
			self.assertFalse((workspace / 'input').exists())
			(src / 'linked').unlink()
			with self.assertRaises(StagingError):
				stage_input(str(src), str(workspace), name='../escape')

	def test_reject_overlap(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			with self.assertRaises(StagingError):
				stage_input(str(base), str(base))


if __name__ == '__main__':
	unittest.main()
