"""Backward-compatible alias for caesar_rest.pipeline.artifacts.discovery."""

import sys

from caesar_rest.pipeline.artifacts import discovery as _module

sys.modules[__name__] = _module
