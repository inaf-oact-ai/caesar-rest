"""Backward-compatible alias for caesar_rest.pipeline.artifacts.binding."""

import sys

from caesar_rest.pipeline.artifacts import binding as _module

sys.modules[__name__] = _module
