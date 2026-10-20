"""Backward-compatible alias for pipeline.submission.slurm_preparation."""

import sys

from caesar_rest.pipeline.submission import slurm_preparation as _module

sys.modules[__name__] = _module
