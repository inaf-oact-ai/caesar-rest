"""Backward-compatible alias for pipeline.staging.ms."""

import sys

from caesar_rest.pipeline.staging import ms as _module

sys.modules[__name__] = _module
