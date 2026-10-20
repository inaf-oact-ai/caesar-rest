"""Backward-compatible alias for pipeline.submission.job_binding."""

import sys

from caesar_rest.pipeline.submission import job_binding as _module

sys.modules[__name__] = _module
