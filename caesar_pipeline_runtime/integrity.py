"""Backward-compatible alias for pipeline_runtime.integrity."""

import sys

from pipeline_runtime import integrity as _module

sys.modules[__name__] = _module
