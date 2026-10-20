"""Regression tests for canonical pipeline imports and compatibility."""

import importlib
import pkgutil
import unittest

import caesar_rest.pipeline as pipeline
import pipeline_runtime


class PipelineImportBoundaryTests(unittest.TestCase):

	def test_canonical_packages_import(self):
		for package in (pipeline, pipeline_runtime):
			for module in pkgutil.walk_packages(
					package.__path__, package.__name__ + '.'):
				with self.subTest(module=module.name):
					importlib.import_module(module.name)

	def test_artifact_module_identity(self):
		from caesar_rest import pipeline_artifact_access as old_access
		from caesar_rest.pipeline.artifacts import access

		from caesar_rest import pipeline_artifact_retention as old_retention
		from caesar_rest.pipeline.artifacts import retention

		self.assertIs(old_access, access)
		self.assertIs(old_retention, retention)

	def test_runtime_module_imports(self):
		from pipeline_runtime import staging
		from pipeline_runtime import executor

		self.assertTrue(callable(staging.stage_inputs))
		self.assertTrue(callable(executor.main))

	def test_core_dependency_identity(self):
		from caesar_rest.pipeline import manager
		from caesar_rest.pipeline.artifacts import access
		from caesar_rest.pipeline.artifacts import retention
		from caesar_rest.pipeline.artifacts import directory_promotion

		self.assertIs(access.manager, manager)
		self.assertIs(retention.manager, manager)
		self.assertIs(directory_promotion.manager, manager)
		self.assertIs(directory_promotion.access, access)
