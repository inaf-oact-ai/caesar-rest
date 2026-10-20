"""Backward-compatible alias for pipeline_runtime.version."""

import sys

from pipeline_runtime import version as _module

sys.modules[__name__] = _module
