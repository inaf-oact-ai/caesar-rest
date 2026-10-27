"""Verify and reuse uncommitted, previously published mixed-run artifacts.

Only call while holding the exclusive per-run .retention.lock. No files are
modified here. Reuse is forbidden unless the retained content is verified.
"""
import hashlib
import os
import stat

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import access
from caesar_rest.pipeline.artifacts import directory_integrity
from caesar_rest.pipeline.artifacts.directory_retention import _open_directory


def _integer(value):
	return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _hash_stream(stream):
	digest = hashlib.sha256()
	count = 0
	while True:
		chunk = stream.read(1024 * 1024)
		if not chunk:
			break
		count += len(chunk)
		digest.update(chunk)
	return count, digest.hexdigest()


def reuse_file(db, owner, run, index, artifact, base, max_file_bytes):
	"""Rehash an existing numbered file AND its authorized original source."""
	size = artifact.get('size_bytes')
	if not _integer(size) or size > max_file_bytes:
		raise manager.PipelineError('Invalid registered file size', 409)
	root_fd = _open_directory(base)
	try:
		fd = os.open('%04d' % index,
			os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
		try:
			info = os.fstat(fd)
			if not stat.S_ISREG(info.st_mode) or info.st_size != size:
				raise manager.PipelineError('Uncommitted retained file differs from registration', 409)
			with os.fdopen(fd, 'rb', closefd=False) as retained:
				count, digest = _hash_stream(retained)
			if count != size or os.fstat(fd).st_size != size:
				raise manager.PipelineError('Uncommitted retained file changed during verification', 409)
		finally:
			os.close(fd)
	finally:
		os.close(root_fd)
	# The previous attempt did not commit the checksum to MongoDB. Compare
	# with the authenticated source, never trust size alone.
	source, _, _ = access.open_registered_artifact(db, owner, run, index)
	with source:
		source_count, source_digest = _hash_stream(source)
	if source_count != size or source_digest != digest:
		raise manager.PipelineError('Uncommitted retained file differs from source', 409)
	return {'index': index, 'size_bytes': size, 'sha256': digest}


def reuse_directory(base, index, artifact, max_bytes, max_entries, max_depth):
	"""Verify a published directory and its immutable sidecar, then recover its record."""
	manifest_name = '%04d.manifest.json' % index
	manifest_path = os.path.join(base, manifest_name)
	if not os.path.lexists(manifest_path):
		raise manager.PipelineError('Published directory lacks integrity manifest; recovery required', 409)
	# Read the sidecar without following links; the integrity verifier later
	# reads and verifies the same on-disk bytes and hashes the complete tree.
	root_fd = _open_directory(base)
	try:
		fd = os.open(manifest_name,
			os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
		try:
			info = os.fstat(fd)
			if not stat.S_ISREG(info.st_mode) or info.st_size > 32 * 1024 * 1024:
				raise manager.PipelineError('Invalid uncommitted directory manifest', 409)
			with os.fdopen(fd, 'rb', closefd=False) as handle:
				payload = handle.read(32 * 1024 * 1024 + 1)
			if len(payload) != info.st_size:
				raise manager.PipelineError('Directory manifest changed while reading', 409)
		finally:
			os.close(fd)
	finally:
		os.close(root_fd)
	import json
	try:
		manifest = json.loads(payload.decode('utf-8'))
	except (ValueError, UnicodeError) as exc:
		raise manager.PipelineError('Invalid uncommitted directory manifest', 409) from exc
	if not isinstance(manifest, dict):
		raise manager.PipelineError('Invalid uncommitted directory manifest', 409)
	for key in ('size_bytes', 'file_count', 'directory_count'):
		value = artifact.get(key)
		if not _integer(value) or manifest.get(key) != value:
			raise manager.PipelineError('Uncommitted directory differs from registered metadata', 409)
	record = {
		'index': index,
		'kind': 'directory',
		'size_bytes': artifact['size_bytes'],
		'file_count': artifact['file_count'],
		'directory_count': artifact['directory_count'],
		'manifest_name': manifest_name,
		'manifest_sha256': hashlib.sha256(payload).hexdigest()
	}
	try:
		directory_integrity.verify_directory_artifact(
			base, index, record, max_entries=max_entries,
			max_bytes=max_bytes, max_depth=max_depth)
	except directory_integrity.DirectoryIntegrityError as exc:
		raise manager.PipelineError('Uncommitted directory failed integrity verification: %s' % exc, 409) from exc
	return record
