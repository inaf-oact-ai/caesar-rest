"""Backward-compatible alias for caesar_rest.pipeline.artifacts.registration."""

import sys

from caesar_rest.pipeline.artifacts import registration as _module

sys.modules[__name__] = _module
