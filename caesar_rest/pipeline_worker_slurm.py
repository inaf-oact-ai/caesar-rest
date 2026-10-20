"""Backward-compatible alias for pipeline.submission.worker_slurm."""

import sys

from caesar_rest.pipeline.submission import worker_slurm as _module

sys.modules[__name__] = _module
