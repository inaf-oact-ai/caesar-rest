"""Backward-compatible import and CLI entry point for pipeline.execution.singularity_synthetic."""

import sys

from caesar_rest.pipeline.execution import singularity_synthetic as _module

if __name__ == '__main__':
	sys.exit(_module.main())

sys.modules[__name__] = _module
