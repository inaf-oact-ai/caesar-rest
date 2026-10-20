"""Backward-compatible alias for pipeline.submission.reconciliation."""

import sys

from caesar_rest.pipeline.submission import reconciliation as _module

sys.modules[__name__] = _module
