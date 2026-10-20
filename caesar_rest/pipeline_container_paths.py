"""Backward-compatible facade; implementation lives in pipeline_runtime."""
from pipeline_runtime import paths as _impl

for _name in dir(_impl):
	if not _name.startswith("__"):
		globals()[_name] = getattr(_impl, _name)

if __name__ == "__main__":
	import sys
	if hasattr(_impl, "main"):
		sys.exit(_impl.main())
