"""Backward-compatible alias for caesar_rest.pipeline.artifacts.retention."""

import sys

from caesar_rest.pipeline.artifacts import retention as _module

sys.modules[__name__] = _module
