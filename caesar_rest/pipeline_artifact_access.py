"""Backward-compatible alias for caesar_rest.pipeline.artifacts.access."""

import sys

from caesar_rest.pipeline.artifacts import access as _module

sys.modules[__name__] = _module
