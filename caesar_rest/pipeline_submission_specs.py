"""Backward-compatible alias for pipeline.staging.submission_specs."""

import sys

from caesar_rest.pipeline.staging import submission_specs as _module

sys.modules[__name__] = _module
