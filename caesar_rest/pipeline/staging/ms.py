"""Backward-compatible Measurement Set adapter for generic staging."""
from pathlib import Path

from pipeline_runtime.staging import StagingError, stage_input


def stage_ms(source, workspace):
	"""Stage one .ms directory; keep the original stage_ms return keys."""
	p = Path(source)
	if p.suffix != '.ms' or not p.is_dir() or p.is_symlink():
		raise StagingError('Source must be an existing non-symlink *.ms directory')
	result = stage_input(source, workspace, mode='copy', writable=True)
	result['private_ms'] = result['private_path']
	return result
