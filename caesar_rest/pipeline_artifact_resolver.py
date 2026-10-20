"""Backward-compatible alias for caesar_rest.pipeline.artifacts.resolver."""

import sys

from caesar_rest.pipeline.artifacts import resolver as _module

sys.modules[__name__] = _module
