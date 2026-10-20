"""Backward-compatible alias for pipeline.artifacts.directory_integrity."""

import sys

from caesar_rest.pipeline.artifacts import directory_integrity as _module

sys.modules[__name__] = _module
