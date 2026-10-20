import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pipeline_runtime import staging, stage_runner, resolver, paths, executor


class SharedRuntimeTests(unittest.TestCase):
	def test_compatibility_facades_are_same_objects(self):
		import caesar_rest.pipeline_data_staging as old_staging
		import caesar_rest.pipeline_stage_runner as old_runner
		import caesar_rest.pipeline_staged_input_resolver as old_resolver
		import caesar_rest.pipeline_container_paths as old_paths
		import caesar_rest.pipeline_container_execution as old_executor
		self.assertIs(old_staging.stage_inputs, staging.stage_inputs)
		self.assertIs(old_staging.StagingError, staging.StagingError)
		self.assertIs(old_runner.prepare, stage_runner.prepare)
		self.assertIs(old_resolver.resolve_staged_inputs, resolver.resolve_staged_inputs)
		self.assertIs(old_paths.map_host_path, paths.map_host_path)
		self.assertIs(old_executor.execute, executor.execute)
		self.assertIs(old_executor.execution_command, executor.execution_command)

	def test_stage_and_resolve_using_shared_runtime(self):
		with tempfile.TemporaryDirectory() as root:
			root = Path(root)
			source = root / 'obs.ms'
			source.mkdir()
			(source / 'table.dat').write_text('test data')
			workspace = root / 'job'
			workspace.mkdir()
			spec = workspace / 'staging_spec.json'
			spec.write_text(json.dumps({'version': 1, 'inputs': [
				{'source': str(source), 'name': 'obs.ms', 'writable': True}]}))
			self.assertEqual(stage_runner.main(['--spec', str(spec), '--workspace', str(workspace)]), 0)
			self.assertEqual(resolver.resolve_staged_inputs(str(workspace))['obs.ms'], str(workspace / 'input' / 'obs.ms'))
			self.assertEqual((source / 'table.dat').read_text(), 'test data')

	def test_runtime_dependency_boundary(self):
		root = Path(staging.__file__).parent
		for path in root.glob('*.py'):
			source = path.read_text()
			self.assertNotIn('from caesar_rest', source)
			self.assertNotIn('import caesar_rest', source)

	def test_old_script_command_still_available(self):
		import caesar_rest.pipeline_container_execution as old
		cmd = old.execution_command('/jobs/a', '/jobs/a/execution_spec.json', '/bin/runner.py')
		self.assertIn('/bin/runner.py', cmd)

if __name__ == '__main__':
	unittest.main()
