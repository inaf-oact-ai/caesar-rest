"""Backward-compatible alias for pipeline.status."""

import sys

from caesar_rest.pipeline import status as _module

sys.modules[__name__] = _module
