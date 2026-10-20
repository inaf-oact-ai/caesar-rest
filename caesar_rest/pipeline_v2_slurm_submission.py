"""Backward-compatible alias for pipeline.submission.slurm_submission."""

import sys

from caesar_rest.pipeline.submission import slurm_submission as _module

sys.modules[__name__] = _module
