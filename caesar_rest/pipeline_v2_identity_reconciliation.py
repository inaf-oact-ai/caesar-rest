"""Backward-compatible alias for pipeline.submission.identity_reconciliation."""

import sys

from caesar_rest.pipeline.submission import identity_reconciliation as _module

sys.modules[__name__] = _module
