"""Backward-compatible alias for pipeline.submission.v2_preparation."""

import sys

from caesar_rest.pipeline.submission import v2_preparation as _module

sys.modules[__name__] = _module
