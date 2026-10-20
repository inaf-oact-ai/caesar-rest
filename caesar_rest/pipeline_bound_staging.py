"""Backward-compatible alias for caesar_rest.pipeline.staging.bound."""

import sys

from caesar_rest.pipeline.staging import bound as _module

sys.modules[__name__] = _module
