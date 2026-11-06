"""Standalone filesystem-based tests; no Flask/MongoDB/casacore required."""

import tempfile
import unittest
from pathlib import Path

from caesar_rest.dataset_inspection.formats import FormatDetectionError, detect_format
from caesar_rest.dataset_inspection.registry import (
	InspectorSelectionError, default_registry, normalize_declared_format
)


REQUIRED = (
	'ANTENNA', 'DATA_DESCRIPTION', 'FEED', 'FIELD', 'OBSERVATION',
	'POLARIZATION', 'SPECTRAL_WINDOW', 'STATE'
)


class InspectionFactoryTests(unittest.TestCase):
	def setUp(self):
		self.temporary = tempfile.TemporaryDirectory()
		self.addCleanup(self.temporary.cleanup)
		self.root = Path(self.temporary.name)
		self.ms = self.root / 'observation-without-ms-extension'
		self.ms.mkdir()
		(self.ms / 'table.dat').touch()
		for name in REQUIRED:
			p = self.ms / name
			p.mkdir()
			(p / 'table.dat').touch()
		self.registry = default_registry('/opt/containers/msv2-inspector.sif')

	def test_msv2_detected_without_extension(self):
		result = self.registry.select(str(self.ms), 'directory', None)
		self.assertEqual(result.status, 'SUPPORTED')
		self.assertEqual(result.detected_format, 'casa-measurement-set-v2')
		self.assertEqual(result.inspector.name, 'msv2-casacore')

	def test_declared_alias(self):
		result = self.registry.select(str(self.ms), 'directory', 'MS')
		self.assertEqual(result.status, 'SUPPORTED')
		self.assertEqual(normalize_declared_format('h5'), 'hdf5')

	def test_mismatch_is_not_overridden(self):
		result = self.registry.select(str(self.ms), 'directory', 'fits')
		self.assertEqual(result.status, 'MISMATCH')
		self.assertIsNone(result.inspector)

	def test_unknown_format_is_unsupported(self):
		unknown = self.root / 'unknown.ms'
		unknown.mkdir()
		result = self.registry.select(str(unknown), 'directory', 'ms')
		self.assertEqual(result.status, 'UNSUPPORTED')

	def test_missing_required_table_is_not_msv2(self):
		(self.ms / 'FIELD' / 'table.dat').unlink()
		result = detect_format(str(self.ms), 'directory')
		self.assertIsNone(result.format)

	def test_symlink_subtable_is_rejected_as_evidence(self):
		(self.ms / 'FIELD' / 'table.dat').unlink()
		(self.ms / 'FIELD' / 'table.dat').symlink_to(self.ms / 'table.dat')
		result = detect_format(str(self.ms), 'directory')
		self.assertIsNone(result.format)

	def test_file_is_not_msv2(self):
		file = self.root / 'fake.ms'
		file.write_bytes(b'plain text')
		result = self.registry.select(str(file), 'file', 'ms')
		self.assertEqual(result.status, 'UNSUPPORTED')

	def test_wrong_type_fails(self):
		with self.assertRaises(FormatDetectionError):
			detect_format(str(self.ms), 'file')

	def test_relative_image_config_rejected(self):
		with self.assertRaises(InspectorSelectionError):
			default_registry('msv2-inspector.sif')


if __name__ == '__main__':
	unittest.main()
