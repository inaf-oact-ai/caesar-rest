"""Backward-compatible alias for pipeline.submission.claimed_preparation."""

import sys

from caesar_rest.pipeline.submission import claimed_preparation as _module

sys.modules[__name__] = _module
