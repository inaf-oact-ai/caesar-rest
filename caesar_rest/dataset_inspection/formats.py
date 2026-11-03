"""Conservative, lightweight identification of registered dataset formats.

All filesystem paths passed to this module must already come from a trusted,
authorized dataset registry lookup. Detection does not open visibility data or
invoke scientific libraries; authoritative MSv2 validation belongs to the
isolated inspector container.
"""

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class FormatDetectionError(ValueError):
	"""The registered path is unavailable or has an unexpected filesystem type."""


@dataclass(frozen=True)
class Detection:
	format: Optional[str]
	evidence: str


def _real_directory(path):
	"""True for a directory without following a symlink at its final component."""
	try:
		mode = os.lstat(str(path)).st_mode
	except (OSError, ValueError):
		return False
	return stat.S_ISDIR(mode)


def _real_file(path):
	"""True for a regular file without following a symlink at its final component."""
	try:
		mode = os.lstat(str(path)).st_mode
	except (OSError, ValueError):
		return False
	return stat.S_ISREG(mode)


def _looks_like_msv2(root):
	"""Identify an MSv2 directory using a conservative filesystem heuristic.

	The casacore MAIN table and required MSv2 subtables are expected to have
	casacore table.dat files. This is NOT a full format validation: the
	scientific inspector must still open and validate these tables read-only.
	"""
	if not _real_directory(root) or not _real_file(root / 'table.dat'):
		return False

	# Required subtables of an ordinary Measurement Set v2. Do not infer
	# validity from a .ms filename or the mere presence of FIELD alone.
	required = (
		'ANTENNA', 'DATA_DESCRIPTION', 'FEED', 'FIELD', 'OBSERVATION',
		'POLARIZATION', 'SPECTRAL_WINDOW', 'STATE'
	)
	for name in required:
		part = root / name
		if not _real_directory(part) or not _real_file(part / 'table.dat'):
			return False
	return True


def detect_format(path, dataset_type):
	"""Return a structural format guess or an unknown result.

	Detection is intentionally narrow in B.2: only an MSv2 signature is
	recognized. Unknown files/directories remain valid registered datasets;
	other format detectors can be added without changing the caller.
	"""
	if dataset_type not in ('file', 'directory'):
		raise FormatDetectionError('Invalid dataset filesystem type')
	if not isinstance(path, (str, os.PathLike)) or not os.path.isabs(path):
		raise FormatDetectionError('Absolute registered dataset path required')

	root = Path(path)
	# Resolve without allowing a symlink at the root; the registry's own
	# validated_path() is responsible for allowed-root checks.
	if dataset_type == 'directory':
		if not _real_directory(root):
			raise FormatDetectionError('Registered dataset directory unavailable or unsafe')
		if _looks_like_msv2(root):
			return Detection('casa-measurement-set-v2', 'casacore-msv2-table-structure')
		return Detection(None, 'unrecognized-directory-structure')

	if not _real_file(root):
		raise FormatDetectionError('Registered dataset file unavailable or unsafe')
	return Detection(None, 'no-supported-file-detector')
