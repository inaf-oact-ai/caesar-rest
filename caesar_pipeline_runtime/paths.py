"""Backward-compatible alias for pipeline_runtime.paths."""

import sys

from pipeline_runtime import paths as _module

sys.modules[__name__] = _module
