"""Pure unit tests for R4C.2B.3 (does not run Singularity/MongoDB)."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

# Allow local tests without installing pymongo; the deployed worker needs it.
if 'pymongo' not in sys.modules:
	try:
		import pymongo
	except ImportError:
		stub = types.ModuleType('pymongo')
		stub.MongoClient = object
		stub.ReturnDocument = types.SimpleNamespace(AFTER='AFTER')
		sys.modules['pymongo'] = stub

spec = importlib.util.spec_from_file_location(
	'run_dataset_inspector', Path(__file__).resolve().parents[1] / 'apps' / 'run_dataset_inspector.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
	def test_rejects_untrusted_path_and_symlink(self):
		with tempfile.TemporaryDirectory() as root:
			p = Path(root) / 'dataset.ms'
			p.mkdir()
			self.assertEqual(worker.validate_dataset_path({'path': str(p), 'type': 'directory'}, [root]), str(p))
			with self.assertRaises(worker.InspectionError):
				worker.validate_dataset_path({'path': str(p), 'type': 'directory'}, ['/other'])
			alias = Path(root) / 'alias.ms'
			alias.symlink_to(p)
			with self.assertRaises(worker.InspectionError):
				worker.validate_dataset_path({'path': str(alias), 'type': 'directory'}, [root])

	def test_result_validation(self):
		with tempfile.TemporaryDirectory() as root:
			spec = types.SimpleNamespace(output_schema='expected', format='msv2', name='inspector')
			doc = {'schema': 'expected', 'format': 'msv2', 'inspector': {'name': 'inspector'},
				'tables': {}, 'field_observations': {}}
			p = Path(root) / 'inspection.json'
			p.write_text(json.dumps(doc))
			self.assertEqual(worker.read_result(root, spec, 4096), doc)
			with self.assertRaises(worker.InspectionError):
				worker.read_result(root, spec, 12)
			p.unlink()
			p.symlink_to(Path(root) / 'nonexistent')
			with self.assertRaises(worker.InspectionError):
				worker.read_result(root, spec, 4096)

	def test_fingerprint_detects_changes(self):
		with tempfile.TemporaryDirectory() as root:
			p = Path(root) / 'data.csv'
			p.write_text('one')
			before = worker.source_fingerprint(str(p), 'file')
			p.write_text('longer contents')
			self.assertNotEqual(before, worker.source_fingerprint(str(p), 'file'))


if __name__ == '__main__':
	unittest.main()
