"""Backward-compatible alias for pipeline_runtime.staging."""

import sys

from pipeline_runtime import staging as _module

sys.modules[__name__] = _module
