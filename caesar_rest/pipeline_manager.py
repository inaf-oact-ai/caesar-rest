"""Backward-compatible alias for caesar_rest.pipeline.manager."""

import sys

from caesar_rest.pipeline import manager as _manager

sys.modules[__name__] = _manager
