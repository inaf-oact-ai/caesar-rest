import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from caesar_rest.pipeline_worker_bundle import build_archive, deploy_worker, WORKER_NAME


class WorkerBundleTests(unittest.TestCase):
	def test_isolated_worker_and_stage(self):
		with tempfile.TemporaryDirectory() as tmp:
			root = Path(tmp)
			worker = root / WORKER_NAME
			digest = build_archive(worker)
			self.assertEqual(len(digest), 64)
			
			# Ensure all runtime dependencies are packaged into the zipapp.
			with zipfile.ZipFile(worker, 'r') as archive:
				self.assertIn(
					'caesar_pipeline_runtime/version.py',
					archive.namelist()
				)
				
			source = root / 'source.txt'
			source.write_text('sample')
			ws = root / 'job'
			ws.mkdir()
			spec = ws / 'staging_spec.json'
			spec.write_text(
				json.dumps({
					'version': 1, 
					'inputs': [
						{
							'source': str(source), 
							'name': 'sample.txt', 
							'mode': 'copy', 
							'writable': True
						}
					]
				})
			)
			
			# The archive runs from an unrelated directory, without the REST tree on PYTHONPATH.
			env = dict(os.environ, PYTHONPATH='')
			completed = subprocess.run([sys.executable, '-I', str(worker), 'prepare', '--workspace', str(ws), '--spec', str(spec)], cwd=tmp, env=env, capture_output=True, text=True)
			self.assertEqual(completed.returncode, 0, completed.stderr)
			self.assertIn('STAGING_READY 1', completed.stdout)
			self.assertEqual((ws / 'input' / 'sample.txt').read_text(), 'sample')

	def test_deployment_rejects_overwrite(self):
		with tempfile.TemporaryDirectory() as tmp:
			ws = Path(tmp) / 'job'
			ws.mkdir()
			info = deploy_worker(str(ws))
			self.assertEqual(info['name'], WORKER_NAME)
			with self.assertRaises(FileExistsError):
				deploy_worker(str(ws))


if __name__ == '__main__':
	unittest.main()
