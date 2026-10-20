"""Backward-compatible alias for pipeline.artifacts.directory_retention."""

import sys

from caesar_rest.pipeline.artifacts import directory_retention as _module

sys.modules[__name__] = _module
