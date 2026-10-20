"""Backward-compatible alias for pipeline.staging.multi_input_specs."""

import sys

from caesar_rest.pipeline.staging import multi_input_specs as _module

sys.modules[__name__] = _module
