"""Backward-compatible alias for caesar_rest.pipeline.routes."""

import sys

from caesar_rest.pipeline import routes as _routes

sys.modules[__name__] = _routes
