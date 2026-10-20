"""Build and place an isolated, standard-library-only pipeline worker archive.

The canonical runtime source is caesar_pipeline_runtime; no source copies are
maintained. A trusted API process deploys this archive into its private job dir.
"""
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import zipfile

from caesar_pipeline_runtime import __file__ as runtime_init

WORKER_NAME = 'caesar-pipeline-worker.pyz'
RUNTIME_MODULES = (
	'__init__.py',
	'version.py',
	'integrity.py',
	'staging.py',
	'stage_runner.py',
	'resolver.py',
	'paths.py',
	'executor.py'
)
ENTRYPOINT = '''"""Offline Slurm pipeline worker."""\nimport sys\nfrom caesar_pipeline_runtime.stage_runner import main as prepare_main\nfrom caesar_pipeline_runtime.executor import main as execute_main\n\ndef main(argv=None):\n	args = sys.argv[1:] if argv is None else argv\n	if not args or args[0] not in ('prepare', 'execute'):\n		print('Usage: caesar-pipeline-worker.pyz {prepare|execute} --workspace PATH --spec PATH', file=sys.stderr)\n		return 2\n	return (prepare_main if args[0] == 'prepare' else execute_main)(args[1:])\n\nif __name__ == '__main__':\n	sys.exit(main())\n'''


def build_archive(destination):
	"""Create deterministic zipapp from the single authoritative source tree."""
	dest = Path(destination)
	source = Path(runtime_init).resolve().parent
	for name in RUNTIME_MODULES:
		candidate = source / name
		if not candidate.is_file() or candidate.is_symlink():
			raise ValueError('Missing or unsafe pipeline runtime module: %s' % name)
	
	if dest.exists() or dest.is_symlink():
		raise FileExistsError('Worker output already exists')
	dest.parent.mkdir(parents=True, exist_ok=True)
	
	try:
		with zipfile.ZipFile(str(dest), 'x', compression=zipfile.ZIP_DEFLATED) as zf:
			def put(name, data):
				info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
				info.compress_type = zipfile.ZIP_DEFLATED
				info.external_attr = (0o644 << 16)
				zf.writestr(info, data)
			put('__main__.py', ENTRYPOINT.encode('utf-8'))
			for name in RUNTIME_MODULES:
				put('caesar_pipeline_runtime/' + name, (source / name).read_bytes())
		dest.chmod(0o600)
		return hashlib.sha256(dest.read_bytes()).hexdigest()
	
	except BaseException:
		dest.unlink(missing_ok=True)
		raise


def deploy_worker(workspace):
	"""Create immutable-by-policy archive before submitting Slurm job.

	The caller guarantees workspace ownership/isolation. The Slurm user must
	have read access to the deployed worker (same as job specs).
	"""
	base = Path(workspace)
	if not base.is_absolute() or base.is_symlink() or not base.is_dir():
		raise ValueError('Invalid job workspace')
	if base.resolve(strict=True) != base:
		raise ValueError('Job workspace must be canonical')
	dest = base / WORKER_NAME
	digest = build_archive(dest)
	return {'name': WORKER_NAME, 'sha256': digest, 'path': str(dest)}
