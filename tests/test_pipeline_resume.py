"""Regression tests for verified reuse of uncommitted mixed-run artifacts."""
import hashlib
import io
import json

import pytest

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.artifacts import resume
from caesar_rest.pipeline.artifacts import directory_retention


def test_reuse_file_compares_source_hash(tmp_path, monkeypatch):
	base = tmp_path / 'retained'
	base.mkdir()
	(base / '0000').write_bytes(b'good')
	from caesar_rest.pipeline.artifacts import access
	monkeypatch.setattr(access, 'open_registered_artifact',
		lambda *args: (io.BytesIO(b'good'), 'file', 'application/octet-stream'))
	record = resume.reuse_file(None, 'alice', {}, 0, {'size_bytes': 4}, str(base), 100)
	assert record['sha256'] == hashlib.sha256(b'good').hexdigest()
	monkeypatch.setattr(access, 'open_registered_artifact',
		lambda *args: (io.BytesIO(b'evil'), 'file', 'application/octet-stream'))
	with pytest.raises(manager.PipelineError, match='differs from source'):
		resume.reuse_file(None, 'alice', {}, 0, {'size_bytes': 4}, str(base), 100)


def test_reuse_directory_checks_contents_and_sidecar(tmp_path):
	base = tmp_path / 'retained'
	base.mkdir()
	source = tmp_path / 'source.ms'
	source.mkdir()
	(source / 'table.dat').write_bytes(b'data')
	meta = {'size_bytes': 4, 'file_count': 1, 'directory_count': 0}
	result = directory_retention.copy_directory_artifact(
		str(source), str(base / '0000'), meta, allow_locked_fallback=True)
	payload = json.dumps(result['manifest'], sort_keys=True,
		separators=(',', ':'), ensure_ascii=False).encode('utf-8')
	(base / '0000.manifest.json').write_bytes(payload)
	record = resume.reuse_directory(str(base), 0, meta, 100, 10, 3)
	assert record['manifest_sha256'] == result['manifest_sha256']
	(source / 'table.dat').write_bytes(b'XXXX')  # retained tree unaffected
	assert resume.reuse_directory(str(base), 0, meta, 100, 10, 3) == record
	(base / '0000' / 'table.dat').write_bytes(b'evil')
	with pytest.raises(manager.PipelineError, match='integrity verification'):
		resume.reuse_directory(str(base), 0, meta, 100, 10, 3)


def test_directory_without_manifest_requires_recovery(tmp_path):
	base = tmp_path / 'retained'
	base.mkdir()
	(base / '0000').mkdir()
	with pytest.raises(manager.PipelineError, match='lacks integrity manifest'):
		resume.reuse_directory(str(base), 0,
			{'size_bytes': 0, 'file_count': 0, 'directory_count': 0}, 100, 10, 3)
