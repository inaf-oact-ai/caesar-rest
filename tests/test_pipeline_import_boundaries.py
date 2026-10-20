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

	def test_runtime_module_identity(self):
		from caesar_pipeline_runtime import staging as old_staging
		from pipeline_runtime import staging

		from caesar_pipeline_runtime import executor as old_executor
		from pipeline_runtime import executor

		self.assertIs(old_staging, staging)
		self.assertIs(old_executor, executor)

	def test_core_dependency_identity(self):
		from caesar_rest.pipeline import manager
		from caesar_rest.pipeline.artifacts import access
		from caesar_rest.pipeline.artifacts import retention
		from caesar_rest.pipeline.artifacts import directory_promotion

		self.assertIs(access.manager, manager)
		self.assertIs(retention.manager, manager)
		self.assertIs(directory_promotion.manager, manager)
		self.assertIs(directory_promotion.access, access)
