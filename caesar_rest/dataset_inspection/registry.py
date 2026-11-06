"""Pure, configurable inspector registry and safe format matching.

No execution, MongoDB calls or Flask context here. The worker will validate
registered path authorization and pass an administrator-supplied image path.
"""

import os
from dataclasses import dataclass
from typing import Optional

from .formats import Detection, detect_format


class InspectorSelectionError(ValueError):
	"""The declared format contradicts detected content or configuration."""


@dataclass(frozen=True)
class InspectorSpec:
	name: str
	format: str
	image: str
	output_schema: str
	execution_backend: str


@dataclass(frozen=True)
class Selection:
	status: str
	detected_format: Optional[str]
	declared_format: Optional[str]
	evidence: str
	inspector: Optional[InspectorSpec]
	reason: Optional[str]


_ALIASES = {
	'ms': 'casa-measurement-set-v2',
	'msv2': 'casa-measurement-set-v2',
	'casa-ms': 'casa-measurement-set-v2',
	'casa-measurement-set-v2': 'casa-measurement-set-v2',
	'fits': 'fits',
	'fit': 'fits',
	'hdf5': 'hdf5',
	'h5': 'hdf5',
	'csv': 'csv',
}


def normalize_declared_format(value):
	"""Canonicalize known aliases without pretending to validate the content."""
	if value is None or value == '':
		return None
	if not isinstance(value, str):
		raise InspectorSelectionError('Declared format must be text')
	value = value.strip().lower()
	return _ALIASES.get(value, value) if value else None


class InspectorRegistry:
	"""Register trusted container-backed inspectors; choose by detected format."""

	def __init__(self, specs):
		self._specs = {}
		for spec in specs:
			if not isinstance(spec, InspectorSpec):
				raise InspectorSelectionError('Invalid inspector specification')
			if spec.format in self._specs:
				raise InspectorSelectionError('Duplicate inspector for format: ' + spec.format)
			if not spec.name or not spec.output_schema:
				raise InspectorSelectionError('Inspector identity and schema required')
			if spec.execution_backend != 'local':
				raise InspectorSelectionError('Only local execution is supported in B.2')
			if not isinstance(spec.image, str) or not os.path.isabs(spec.image):
				raise InspectorSelectionError('Inspector image must have an absolute path')
			if os.path.normpath(spec.image) != spec.image or spec.image == '/':
				raise InspectorSelectionError('Inspector image path must be normalized')
			self._specs[spec.format] = spec

	def select(self, path, dataset_type, declared_format=None):
		"""Select a supported inspector or explain why none can be selected.

		When a real format is detected and the declared format conflicts,
		return MISMATCH, not a silent override. Unknown detection cannot
		confirm or refute a declaration, so return UNSUPPORTED for now.
		"""
		declared = normalize_declared_format(declared_format)
		detected = detect_format(path, dataset_type)
		if detected.format is None:
			return Selection(
				status='UNSUPPORTED', detected_format=None,
				declared_format=declared, evidence=detected.evidence,
				inspector=None, reason='No supported format positively detected'
			)
		if declared and declared != detected.format:
			return Selection(
				status='MISMATCH', detected_format=detected.format,
				declared_format=declared, evidence=detected.evidence,
				inspector=None, reason='Declared format differs from detected format'
			)
		spec = self._specs.get(detected.format)
		if spec is None:
			return Selection(
				status='UNSUPPORTED', detected_format=detected.format,
				declared_format=declared, evidence=detected.evidence,
				inspector=None, reason='No inspector registered for detected format'
			)
		return Selection(
			status='SUPPORTED', detected_format=detected.format,
			declared_format=declared, evidence=detected.evidence,
			inspector=spec, reason=None
		)


def default_registry(msv2_image):
	"""Create a local-only registry using trusted server configuration."""
	return InspectorRegistry([
		InspectorSpec(
			name='msv2-casacore',
			format='casa-measurement-set-v2',
			image=msv2_image,
			output_schema='caesar.dataset-inspection.msv2.v1',
			execution_backend='local'
		)
	])
