"""Opt-in, owner-scoped promotion of registered pipeline result files.

No Slurm operations or scientific-state updates.  A successful promotion is
published only after all registered files have been safely copied and checked.
"""
import hashlib
import os
import re
import tempfile

from caesar_rest import pipeline_manager as manager
from caesar_rest import pipeline_artifact_access as access

_SAFE = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def retained_directory(root, owner, pipeline_id, run_id):
    if not isinstance(root, str) or not os.path.isabs(root) or root == '/':
        raise manager.PipelineError('Invalid artifact retention root', 503)
    if not all(isinstance(v, str) and _SAFE.fullmatch(v)
               for v in (owner, pipeline_id, run_id)):
        raise manager.PipelineError('Invalid artifact retention identity', 409)
    return os.path.join(root, owner, pipeline_id, run_id)


def _mkdir_safe(path):
    # Reject symlinks even in pre-existing parent directories.
    path = os.path.abspath(path)
    cur = os.path.sep
    for part in path.split(os.path.sep)[1:]:
        if not part:
            continue
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise manager.PipelineError('Unsafe artifact retention directory', 409)
        if not os.path.exists(cur):
            os.mkdir(cur, 0o700)
        if not os.path.isdir(cur):
            raise manager.PipelineError('Invalid artifact retention directory', 409)


def promote_run(db, owner, pipeline_id, node_id, run_id, root,
                max_file_bytes=1024 * 1024 * 1024):
    """Copy every registered artifact and publish a durable per-run record.

    Returns a public summary. Safe to retry after partial copy; never deletes
    source files. A concurrent successful promotion wins the DB update.
    """
    run = access.get_run(db, owner, pipeline_id, node_id, run_id)
    if run.get('status') != 'COMPLETED' or not run.get('artifacts_registered_at'):
        raise manager.PipelineError('Run artifacts are not registered', 409)
    existing = run.get('retained_artifacts')
    if existing is not None:
        return {'run_id': run_id, 'retained': True, 'count': len(existing),
                'already_retained': True}
    artifacts = run.get('artifacts') or []
    if not artifacts:
        raise manager.PipelineError('No artifacts registered', 409)
    if not isinstance(max_file_bytes, int) or max_file_bytes <= 0:
        raise manager.PipelineError('Invalid artifact retention size limit', 503)
    base = retained_directory(root, owner, pipeline_id, run_id)
    try:
        _mkdir_safe(base)
        records = []
        for index, artifact in enumerate(artifacts):
            size = artifact.get('size_bytes')
            if not isinstance(size, int) or size < 0 or size > max_file_bytes:
                raise manager.PipelineError('Artifact exceeds retention limit', 413)
            # Existing H1C logic validates job ownership, link safety and size.
            source, _, _ = access.open_registered_artifact(db, owner, run, index)
            target_name = '%04d' % index
            target = os.path.join(base, target_name)
            try:
                tmp_fd, tmp_name = tempfile.mkstemp(prefix='.pending-', dir=base)
            except BaseException:
                source.close()
                raise
            digest = hashlib.sha256()
            count = 0
            try:
                with source, os.fdopen(tmp_fd, 'wb') as output:
                    while True:
                        block = source.read(min(1024 * 1024, max_file_bytes + 1 - count))
                        if not block:
                            break
                        count += len(block)
                        if count > max_file_bytes or count > size:
                            raise manager.PipelineError('Artifact changed during retention', 409)
                        output.write(block)
                        digest.update(block)
                    output.flush()
                    os.fsync(output.fileno())
                if count != size:
                    raise manager.PipelineError('Artifact changed during retention', 409)
                # Atomic per-file replacement. Concurrent requests are serialized
                # only by the final MongoDB compare-and-set.
                os.replace(tmp_name, target)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            records.append({'index': index, 'sha256': digest.hexdigest(),
                            'size_bytes': count})
        result = db.pipeline_runs.update_one(
            {'owner': owner, 'pipeline_id': pipeline_id, 'node_id': node_id,
             'run_id': run_id, 'status': 'COMPLETED',
             'retained_artifacts': {'$exists': False}},
            {'$set': {'retained_artifacts': records,
                      'retained_at': manager.utcnow()}})
        if not result.modified_count:
            latest = db.pipeline_runs.find_one({'owner': owner, 'pipeline_id': pipeline_id,
                                               'node_id': node_id, 'run_id': run_id})
            if not latest or latest.get('retained_artifacts') is None:
                raise manager.PipelineError('Artifact retention not recorded', 409)
        return {'run_id': run_id, 'retained': True,
                'count': len(records), 'already_retained': False}
    except OSError:
        raise manager.PipelineError('Artifact retention storage failure', 503)
