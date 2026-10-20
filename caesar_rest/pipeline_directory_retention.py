"""Safe, bounded and atomic copy of a registered directory artifact.

This is a storage primitive, not a run-level retention operation. It does not
update MongoDB or change the existing file-artifact download behavior.
"""
import hashlib
import json
import os
import re
import stat
import tempfile


class DirectoryRetentionError(ValueError):
	pass


def _limit(value, name):
	if type(value) is not int or value < 1:
		raise DirectoryRetentionError('Invalid ' + name)
	return value


def _component(name):
	if (not isinstance(name, str) or not name or name in ('.', '..')
			or '/' in name or '\\' in name or '\x00' in name):
		raise DirectoryRetentionError('Invalid directory entry')
	return name


def _dirflags():
	return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_directory(path):
	"""Open a directory through descriptors rooted at /, rejecting symlinks."""
	if not isinstance(path, str) or not os.path.isabs(path):
		raise DirectoryRetentionError('Directory path must be absolute')
	fd = os.open('/', _dirflags())
	try:
		for part in path.split('/'):
			if part:
				new_fd = os.open(_component(part), _dirflags(), dir_fd=fd)
				os.close(fd)
				fd = new_fd
		return fd
	except BaseException:
		os.close(fd)
		raise


def _sync_dir(path):
	fd = _open_directory(path)
	try:
		os.fsync(fd)
	finally:
		os.close(fd)


def copy_directory_artifact(source, destination, expected,
		max_bytes=1024 * 1024 * 1024 * 1024,
		max_entries=100000, max_depth=16):
	"""Copy one directory, publish atomically, and return its integrity manifest.

	The destination must not exist. Its parent must exist and be trusted; both
	source and destination are absolute paths. No symlink or special file is
	accepted. SHA-256 is computed while copying; no file is followed by path.
	The manifest includes directories so empty subdirectories are preserved.
	"""
	max_bytes = _limit(max_bytes, 'directory size limit')
	max_entries = _limit(max_entries, 'directory entry limit')
	max_depth = _limit(max_depth, 'directory depth limit')
	if not isinstance(expected, dict):
		raise DirectoryRetentionError('Missing discovery metadata')
	if not isinstance(destination, str) or not os.path.isabs(destination):
		raise DirectoryRetentionError('Destination must be absolute')
	if not isinstance(source, str) or not os.path.isabs(source):
		raise DirectoryRetentionError('Source must be absolute')
	if os.path.lexists(destination):
		raise DirectoryRetentionError('Destination already exists')
	parent = os.path.dirname(destination)
	name = _component(os.path.basename(destination))
	parent_fd = None
	src_fd = None
	tmp = None
	try:
		src_fd = _open_directory(source)
		parent_fd = _open_directory(parent)
		# Keep the private staging directory inside the destination filesystem.
		tmp = tempfile.mkdtemp(prefix='.pending-directory-', dir=parent)
		os.chmod(tmp, 0o700)
		total = 0
		files = 0
		dirs = 0
		entries = []

		def walk(src, dst, prefix, depth):
			nonlocal total, files, dirs
			for entry in sorted(os.listdir(src), key=lambda s: s.encode('utf-8')):
				_component(entry)
				info = os.stat(entry, dir_fd=src, follow_symlinks=False)
				relative = prefix + entry
				if stat.S_ISDIR(info.st_mode):
					if depth + 1 > max_depth:
						raise DirectoryRetentionError('Directory depth limit exceeded')
					dirs += 1
					if files + dirs > max_entries:
						raise DirectoryRetentionError('Directory entry limit exceeded')
					child_src = os.open(entry, _dirflags(), dir_fd=src)
					try:
						os.mkdir(entry, 0o700, dir_fd=dst)
						child_dst = os.open(entry, _dirflags(), dir_fd=dst)
						try:
							entries.append({'path': relative + '/', 'kind': 'directory'})
							walk(child_src, child_dst, relative + '/', depth + 1)
							os.fsync(child_dst)
						finally:
							os.close(child_dst)
					finally:
						os.close(child_src)
				elif stat.S_ISREG(info.st_mode):
					files += 1
					if files + dirs > max_entries:
						raise DirectoryRetentionError('Directory entry limit exceeded')
					if total + info.st_size > max_bytes:
						raise DirectoryRetentionError('Directory size limit exceeded')
					fd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=src)
					try:
						opened = os.fstat(fd)
						if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
							raise DirectoryRetentionError('Source changed while copying')
						out_fd = os.open(entry, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dst)
						try:
							hash_obj = hashlib.sha256()
							count = 0
							while True:
								chunk = os.read(fd, 1024 * 1024)
								if not chunk:
									break
								count += len(chunk)
								if total + count > max_bytes or count > info.st_size:
									raise DirectoryRetentionError('Source size changed while copying')
								hash_obj.update(chunk)
								view = memoryview(chunk)
								while view:
									view = view[os.write(out_fd, view):]
							os.fsync(out_fd)
						finally:
							os.close(out_fd)
						if count != info.st_size or os.fstat(fd).st_size != info.st_size:
							raise DirectoryRetentionError('Source size changed while copying')
						total += count
						entries.append({'path': relative, 'kind': 'file', 'size_bytes': count,
							'sha256': hash_obj.hexdigest()})
					finally:
						os.close(fd)
				else:
					raise DirectoryRetentionError('Symlink or special file rejected')

		tmp_fd = _open_directory(tmp)
		try:
			walk(src_fd, tmp_fd, '', 0)
			os.fsync(tmp_fd)
		finally:
			os.close(tmp_fd)
		for key, value in [('size_bytes', total), ('file_count', files), ('directory_count', dirs)]:
			if type(expected.get(key)) is not int or expected[key] != value:
				raise DirectoryRetentionError('Directory changed since discovery: ' + key)
		manifest = {'version': 1, 'kind': 'directory', 'size_bytes': total,
			'file_count': files, 'directory_count': dirs, 'entries': entries}
		manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
		manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
		# Separate sidecar in temporary tree is intentionally avoided: preserve
		# exact scientific contents; caller stores manifest in metadata.
		if os.path.lexists(destination):
			raise DirectoryRetentionError('Destination already exists')
		os.rename(tmp, destination)
		tmp = None
		os.fsync(parent_fd)
		return {'kind': 'directory', 'size_bytes': total, 'file_count': files,
			'directory_count': dirs, 'manifest_sha256': manifest_sha256,
			'manifest': manifest}
	finally:
		if src_fd is not None:
			os.close(src_fd)
		if parent_fd is not None:
			os.close(parent_fd)
		if tmp is not None:
			# Remove only the known private temporary tree; never follow links.
			import shutil
			shutil.rmtree(tmp)
