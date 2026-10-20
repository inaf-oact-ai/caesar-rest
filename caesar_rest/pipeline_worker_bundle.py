"""Backward-compatible alias for pipeline.submission.worker_bundle."""

import sys

from caesar_rest.pipeline.submission import worker_bundle as _module

sys.modules[__name__] = _module
