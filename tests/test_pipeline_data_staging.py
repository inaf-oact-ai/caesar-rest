import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from caesar_rest.pipeline_data_staging import stage_input, stage_inputs, StagingError
from caesar_rest.pipeline_ms_staging import stage_ms


class StageTests(unittest.TestCase):
	def test_ms_compatibility_and_independence(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			src = base / 'observation.ms'
			src.mkdir()
			(src / 'table.dat').write_bytes(b'original')
			workspace = base / 'job'
			workspace.mkdir()
			result = stage_ms(str(src), str(workspace))
			Path(result['private_ms'], 'table.dat').write_bytes(b'changed')
			self.assertEqual((src / 'table.dat').read_bytes(), b'original')
			self.assertEqual(result['staging_state'], 'READY')
			with self.assertRaises(StagingError):
				stage_ms(str(src), str(workspace))

	def test_multiple_named_inputs(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			ms = base / 'obs.ms'
			ms.mkdir()
			(ms / 'table.dat').write_bytes(b'original')
			cfg = base / 'config.yaml'
			cfg.write_text('original')
			ws = base / 'job'
			ws.mkdir()
			manifest = stage_inputs([
				{'source': str(ms), 'name': 'science.ms', 'writable': True},
				{'source': str(cfg), 'name': 'settings.yaml', 'writable': False},
			], str(ws))
			self.assertEqual(manifest['staging_state'], 'READY')
			self.assertEqual(len(manifest['inputs']), 2)
			self.assertFalse((ws / 'input' / 'settings.yaml').stat().st_mode & 0o222)
			(self._path(manifest, 'science.ms') / 'table.dat').write_bytes(b'changed')
			self.assertEqual((ms / 'table.dat').read_bytes(), b'original')
			self.assertEqual(json.loads((ws / 'input' / 'staging.json').read_text()), manifest)

	def _path(self, manifest, name):
		return Path(next(v['private_path'] for v in manifest['inputs'] if v['name'] == name))

	def test_duplicate_names_preflight_no_directory(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			a = base / 'a'
			a.write_text('a')
			ws = base / 'job'
			ws.mkdir()
			with self.assertRaises(StagingError):
				stage_inputs([{'source': str(a), 'name': 'same'}, {'source': str(a), 'name': 'same'}], str(ws))
			self.assertFalse((ws / 'input').exists())

	def test_copy_failure_no_ready(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			s = base / 'file'
			s.write_text('x')
			ws = base / 'job'
			ws.mkdir()
			with patch('caesar_rest.pipeline_data_staging.shutil.copy2', side_effect=OSError('disk full')):
				with self.assertRaises(StagingError):
					stage_inputs([{'source': str(s)}], str(ws))
			self.assertTrue((ws / 'input').is_dir())
			self.assertFalse((ws / 'input' / 'staging.json').exists())

	def test_symlink_rejected(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			src = base / 'obs.ms'
			src.mkdir()
			(src / 'link').symlink_to('/tmp')
			ws = base / 'job'
			ws.mkdir()
			with self.assertRaises(StagingError):
				stage_inputs([{'source': str(src)}], str(ws))
			self.assertFalse((ws / 'input').exists())

	def test_overlap_and_invalid_names(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			ws = base / 'job'
			ws.mkdir()
			with self.assertRaises(StagingError):
				stage_inputs([{'source': str(base)}], str(ws))
			self.assertFalse((ws / 'input').exists())
			s = base / 'config'
			s.write_text('x')
			for name in ('../escape', 'staging.json', ''):
				with self.assertRaises(StagingError):
					stage_inputs([{'source': str(s), 'name': name}], str(ws))

	def test_single_file_compatibility(self):
		with tempfile.TemporaryDirectory() as td:
			base = Path(td)
			s = base / 'image.fits'
			s.write_bytes(b'fits')
			ws = base / 'job'
			ws.mkdir()
			result = stage_input(str(s), str(ws))
			self.assertEqual(result['input_type'], 'file')
			self.assertEqual(result['staging_state'], 'READY')
			self.assertEqual(result['private_path'], str(ws / 'input' / 'image.fits'))


if __name__ == '__main__':
	unittest.main()
