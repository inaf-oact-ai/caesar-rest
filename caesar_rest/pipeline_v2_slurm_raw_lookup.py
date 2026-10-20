"""Backward-compatible alias for pipeline.submission.slurm_raw_lookup."""

import sys

from caesar_rest.pipeline.submission import slurm_raw_lookup as _module

sys.modules[__name__] = _module
