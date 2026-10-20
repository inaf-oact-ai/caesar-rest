"""Backward-compatible alias for pipeline.artifacts.directory_promotion."""

import sys

from caesar_rest.pipeline.artifacts import directory_promotion as _module

sys.modules[__name__] = _module
