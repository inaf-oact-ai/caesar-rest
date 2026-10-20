"""Backward-compatible alias for caesar_rest.pipeline.staging.workspace."""

import sys

from caesar_rest.pipeline.staging import workspace as _module

sys.modules[__name__] = _module
