"""Backward-compatible alias for pipeline_runtime.resolver."""

import sys

from pipeline_runtime import resolver as _module

sys.modules[__name__] = _module
