"""Backward-compatible alias for pipeline.submission.v2_adapter."""

import sys

from caesar_rest.pipeline.submission import v2_adapter as _module

sys.modules[__name__] = _module
