"""Backward-compatible alias for pipeline.artifacts.directory_resolver."""

import sys

from caesar_rest.pipeline.artifacts import directory_resolver as _module

sys.modules[__name__] = _module
