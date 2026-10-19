import pytest
from caesar_rest.pipeline_artifact_discovery import ArtifactDiscoveryError, discover_artifacts


CONTRACT = {
    'manifest': {'path': 'oxkat_manifest.json', 'required': True, 'type': 'application/json', 'role': 'primary_result'},
    'log': {'glob': '*.log', 'required': False, 'type': 'text/plain', 'role': 'diagnostic'},
}


def test_discovers_only_results(tmp_path):
    results = tmp_path / 'results'
    results.mkdir()
    (tmp_path / 'input').mkdir()
    (tmp_path / 'input' / 'large.ms').write_bytes(b'x' * 10)
    (results / 'oxkat_manifest.json').write_text('{}')
    (results / 'run.log').write_text('ok')
    artifacts = discover_artifacts(str(tmp_path), CONTRACT)
    assert [item['relative_path'] for item in artifacts] == ['results/run.log', 'results/oxkat_manifest.json']
    assert artifacts[1]['size_bytes'] == 2


def test_required_missing(tmp_path):
    (tmp_path / 'results').mkdir()
    with pytest.raises(ArtifactDiscoveryError, match='Missing required'):
        discover_artifacts(str(tmp_path), CONTRACT)


def test_rejects_symlink(tmp_path):
    results = tmp_path / 'results'
    results.mkdir()
    target = tmp_path / 'secret'
    target.write_text('secret')
    (results / 'oxkat_manifest.json').symlink_to(target)
    with pytest.raises(ArtifactDiscoveryError, match='Symlink'):
        discover_artifacts(str(tmp_path), CONTRACT)


def test_rejects_traversal(tmp_path):
    (tmp_path / 'results').mkdir()
    with pytest.raises(ArtifactDiscoveryError, match='relative'):
        discover_artifacts(str(tmp_path), {'bad': {'path': '../secret', 'required': True}})


def test_limits_outputs(tmp_path):
    results = tmp_path / 'results'
    results.mkdir()
    (results / 'a.log').write_text('a')
    (results / 'b.log').write_text('b')
    with pytest.raises(ArtifactDiscoveryError, match='limit'):
        discover_artifacts(str(tmp_path), {'logs': {'glob': '*.log'}}, max_files=1)
