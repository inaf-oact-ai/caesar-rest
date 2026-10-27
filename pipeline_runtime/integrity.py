"""Offline V2 staged-copy verification; Python standard library only.

The expected hashes travel in the trusted job-local staging specification.
This module never reads mutable upstream manifests during Slurm staging.
"""
import hashlib
import os
import re
import stat
from pathlib import Path

_SHA = re.compile(r'^[0-9a-f]{64}$')


def _valid_path(value, directory):
	if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
		return False
	if value.startswith('/') or value.startswith('./') or '//' in value:
		return False
	if value.endswith('/') != directory:
		return False
	parts = value.rstrip('/').split('/')
	return all(p not in ('', '.', '..') for p in parts)


def validate_expected(item, kind):
	"""Reject malformed checksum contracts before filesystem access."""
	if kind == 'file':
		if 'manifest_entries' in item or not isinstance(item.get('sha256'), str) or not _SHA.fullmatch(item['sha256']):
			raise ValueError('Invalid SHA-256')
	elif kind == 'directory':
		if 'sha256' in item:
			raise ValueError('Unexpected file digest')
		entries = item.get('manifest_entries')
		if not isinstance(entries, list) or len(entries) > 100000:
			raise ValueError('Invalid directory entries')
		seen = set()
		for entry in entries:
			if not isinstance(entry, dict) or entry.get('kind') not in ('directory', 'file'):
				raise ValueError('Invalid entry')
			is_dir = entry['kind'] == 'directory'
			if set(entry) != ({'path', 'kind'} if is_dir else {'path', 'kind', 'size_bytes', 'sha256'}):
				raise ValueError('Invalid entry fields')
			path = entry['path']
			if not _valid_path(path, is_dir) or path in seen:
				raise ValueError('Invalid or repeated path')
			seen.add(path)
			if not is_dir and (type(entry.get('size_bytes')) is not int or entry['size_bytes'] < 0 or
					not isinstance(entry.get('sha256'), str) or not _SHA.fullmatch(entry['sha256'])):
				raise ValueError('Invalid file entry digest')
	else:
		raise ValueError('Invalid kind')


def _digest(path):
	h = hashlib.sha256()
	with open(str(path), 'rb') as stream:
		while True:
			chunk = stream.read(1024 * 1024)
			if not chunk:
				break
			h.update(chunk)
	return h.hexdigest()


def verify_copy(path, descriptor):
	"""Check exact staged bytes and directory structure before READY."""
	kind = descriptor['kind']
	validate_expected(descriptor, kind)
	root = Path(path)
	if root.is_symlink():
		raise ValueError('Symlink at staged root')
	if kind == 'file':
		if not stat.S_ISREG(root.lstat().st_mode) or _digest(root) != descriptor['sha256']:
			raise ValueError('Staged file checksum mismatch')
		return True
	if not stat.S_ISDIR(root.lstat().st_mode):
		raise ValueError('Staged input is not a directory')
	actual = []
	def walk(directory, prefix):
		for child in sorted(directory.iterdir(), key=lambda p: p.name.encode('utf-8')):
			mode = child.lstat().st_mode
			rel = prefix + child.name
			if stat.S_ISDIR(mode):
				actual.append({'path': rel + '/', 'kind': 'directory'})
				walk(child, rel + '/')
			elif stat.S_ISREG(mode):
				actual.append({'path': rel, 'kind': 'file',
					'size_bytes': child.stat().st_size, 'sha256': _digest(child)})
			else:
				raise ValueError('Symlink or special file in staged directory')
	walk(root, '')
	if actual != descriptor['manifest_entries']:
		raise ValueError('Staged directory manifest mismatch')
	return True
