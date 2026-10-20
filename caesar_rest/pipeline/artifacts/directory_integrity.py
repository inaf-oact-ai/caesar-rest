"""Read-only verification of retained directory artifacts and their sidecars.

No cleanup, no source workspace access, no client-selected paths.
"""
import hashlib
import json
import os
import re
import stat

from caesar_rest.pipeline.artifacts.directory_retention import _open_directory, _component, _dirflags


class DirectoryIntegrityError(ValueError):
	pass


def _read_sidecar(base, filename, limit):
	fd = _open_directory(base)
	try:
		name = _component(filename)
		file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
		try:
			info = os.fstat(file_fd)
			if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
				raise DirectoryIntegrityError('Invalid directory manifest file')
			with os.fdopen(file_fd, 'rb', closefd=False) as stream:
				data = stream.read(limit + 1)
			if len(data) != info.st_size:
				raise DirectoryIntegrityError('Directory manifest changed while reading')
			return data
		finally:
			os.close(file_fd)
	finally:
		os.close(fd)


def verify_directory_artifact(base, index, record, max_entries=100000, max_bytes=1024 * 1024 * 1024 * 1024,
		max_depth=16, max_manifest_bytes=32 * 1024 * 1024):
	"""Verify exact contents and manifest of a retained directory.

	The returned metadata is safe for status reporting; the directory itself
	must be reopened and reverified before downstream consumption.
	"""
	if type(index) is not int or index < 0 or not isinstance(record, dict):
		raise DirectoryIntegrityError('Invalid directory artifact identity')
	name = '%04d' % index
	manifest_name = name + '.manifest.json'
	if record.get('index') != index or record.get('kind') != 'directory' or record.get('manifest_name') != manifest_name:
		raise DirectoryIntegrityError('Invalid directory artifact metadata')
	sha = record.get('manifest_sha256')
	if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
		raise DirectoryIntegrityError('Invalid directory manifest digest')
	if any(type(value) is not int or value < 0 for value in
		(record.get('size_bytes'), record.get('file_count'), record.get('directory_count'))):
		raise DirectoryIntegrityError('Invalid directory counts')
	if any(type(x) is not int or x < 1 for x in (max_entries, max_bytes, max_depth, max_manifest_bytes)):
		raise DirectoryIntegrityError('Invalid verification limits')
	try:
		data = _read_sidecar(base, manifest_name, max_manifest_bytes)
		if hashlib.sha256(data).hexdigest() != sha:
			raise DirectoryIntegrityError('Directory manifest checksum mismatch')
		manifest = json.loads(data.decode('utf-8'))
		if not isinstance(manifest, dict) or manifest.get('version') != 1 or manifest.get('kind') != 'directory':
			raise DirectoryIntegrityError('Invalid directory manifest')
		for field in ('size_bytes', 'file_count', 'directory_count'):
			if manifest.get(field) != record.get(field):
				raise DirectoryIntegrityError('Directory manifest metadata mismatch')
		expected = manifest.get('entries')
		if not isinstance(expected, list) or len(expected) > max_entries:
			raise DirectoryIntegrityError('Invalid directory manifest entries')
		root_fd = _open_directory(base)
		try:
			target_fd = os.open(name, _dirflags(), dir_fd=root_fd)
			try:
				actual = []
				total = 0
				files = 0
				dirs = 0
				def walk(parent, prefix, depth):
					nonlocal total, files, dirs
					for child in sorted(os.listdir(parent), key=lambda s: s.encode('utf-8')):
						_component(child)
						info = os.stat(child, dir_fd=parent, follow_symlinks=False)
						relative = prefix + child
						if stat.S_ISDIR(info.st_mode):
							if depth + 1 > max_depth:
								raise DirectoryIntegrityError('Directory depth limit exceeded')
							dirs += 1
							if files + dirs > max_entries:
								raise DirectoryIntegrityError('Directory entry limit exceeded')
							fd = os.open(child, _dirflags(), dir_fd=parent)
							try:
								actual.append({'path': relative + '/', 'kind': 'directory'})
								walk(fd, relative + '/', depth + 1)
							finally:
								os.close(fd)
						elif stat.S_ISREG(info.st_mode):
							files += 1
							if files + dirs > max_entries:
								raise DirectoryIntegrityError('Directory entry limit exceeded')
							fd = os.open(child, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
							try:
								opened = os.fstat(fd)
								if not stat.S_ISREG(opened.st_mode) or (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
									raise DirectoryIntegrityError('Directory file changed while opening')
								digest = hashlib.sha256()
								count = 0
								while True:
									chunk = os.read(fd, 1024 * 1024)
									if not chunk:
										break
									count += len(chunk)
									if total + count > max_bytes or count > info.st_size:
										raise DirectoryIntegrityError('Directory size limit exceeded')
									digest.update(chunk)
								if count != info.st_size or os.fstat(fd).st_size != info.st_size:
									raise DirectoryIntegrityError('Directory file size changed')
								total += count
								actual.append({'path': relative, 'kind': 'file', 'size_bytes': count, 'sha256': digest.hexdigest()})
							finally:
								os.close(fd)
						else:
							raise DirectoryIntegrityError('Special file in retained directory')
				walk(target_fd, '', 0)
			finally:
				os.close(target_fd)
		finally:
			os.close(root_fd)
		if actual != expected or (total, files, dirs) != (
			record['size_bytes'], record['file_count'], record['directory_count']):
			raise DirectoryIntegrityError('Retained directory contents mismatch')
		return {'verified': True, 'index': index, 'size_bytes': total, 'file_count': files, 'directory_count': dirs}
	except (OSError, ValueError, UnicodeError, TypeError, KeyError) as exc:
		if isinstance(exc, DirectoryIntegrityError):
			raise
		raise DirectoryIntegrityError('Cannot safely verify retained directory') from exc
