"""Backward-compatible CLI and module alias for pipeline_runtime.stage_runner."""

import sys

from pipeline_runtime import stage_runner as _module

if __name__ == '__main__':
	sys.exit(_module.main())

sys.modules[__name__] = _module
