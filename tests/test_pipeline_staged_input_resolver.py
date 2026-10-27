import json
import tempfile
import unittest
from pathlib import Path

from pipeline_runtime.staging import StagingError, stage_inputs
from pipeline_runtime.resolver import resolve_staged_inputs


class ResolverTests(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		root = Path(self.tmp.name)
		self.source = root / 'sample.fits'
		self.source.write_bytes(b'fits')
		self.workspace = root / 'job'
		self.workspace.mkdir()

	def stage(self):
		stage_inputs([{'source': str(self.source), 'name': 'science.fits', 'writable': False}], str(self.workspace))

	def update_manifest(self, callback):
		path = self.workspace / 'input' / 'staging.json'
		manifest = json.loads(path.read_text())
		callback(manifest)
		path.write_text(json.dumps(manifest))

	def test_valid_ready(self):
		self.stage()
		found = resolve_staged_inputs(str(self.workspace), ['science.fits'])
		self.assertEqual(found['science.fits'], str(self.workspace / 'input' / 'science.fits'))

	def test_manifest_missing(self):
		with self.assertRaises(StagingError):
			resolve_staged_inputs(str(self.workspace))

	def test_not_ready(self):
		self.stage()
		self.update_manifest(lambda m: m.update(staging_state='FAILED'))
		with self.assertRaises(StagingError):
			resolve_staged_inputs(str(self.workspace))

	def test_forged_private_path(self):
		self.stage()
		self.update_manifest(lambda m: m['inputs'][0].update(private_path='/etc/passwd'))
		with self.assertRaises(StagingError):
			resolve_staged_inputs(str(self.workspace))

	def test_reject_staged_symlink(self):
		self.stage()
		p = self.workspace / 'input' / 'science.fits'
		p.unlink()
		p.symlink_to(self.source)
		with self.assertRaises(StagingError):
			resolve_staged_inputs(str(self.workspace))

	def test_missing_required_name(self):
		self.stage()
		with self.assertRaises(StagingError):
			resolve_staged_inputs(str(self.workspace), ['missing'])

	def test_duplicate_name(self):
		self.stage()
		self.update_manifest(lambda m: m['inputs'].append(dict(m['inputs'][0])))
		with self.assertRaises(StagingError):
			resolve_staged_inputs(str(self.workspace))

	def test_directory_nested_symlink(self):
		folder = Path(self.tmp.name) / 'dir'
		folder.mkdir()
		(folder / 'data').write_text('data')
		stage_inputs([{'source': str(folder), 'name': 'solutions.tbl'}], str(self.workspace))
		staged = self.workspace / 'input' / 'solutions.tbl'
		(staged / 'link').symlink_to(self.source)
		with self.assertRaises(StagingError):
			resolve_staged_inputs(str(self.workspace))


if __name__ == '__main__':
	unittest.main()
