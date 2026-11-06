# Pipeline artifact retention

CAESAR-REST provides a standalone artifact retention worker responsible for preserving registered outputs of completed scientific pipeline runs.

The worker runs independently of the REST application and the job monitoring service. It periodically queries MongoDB for eligible pipeline runs and promotes their registered artifacts into persistent storage, performing integrity and safety checks before publishing the retained outputs.

The artifact lifecycle consists of four steps:

1. A scientific job completes successfully and its associated pipeline run transitions to `COMPLETED`.
2. The job monitoring service registers the run's output artifacts in MongoDB.
3. The artifact retention worker copies and verifies those artifacts into persistent retention storage.
4. The retained artifacts become available for downstream pipeline stages.

**Persistent artifact retention is required for multi-stage Pipeline V2 workflows.** Downstream stages consume verified retained artifacts, rather than relying on files remaining in previous job working directories.

The standalone worker is the recommended retention mechanism for current deployments. It provides a durable MongoDB-backed processing queue and allows large scientific outputs to be retained independently of job-status monitoring.

For related configuration, see [Job monitoring](job-monitoring.md) and [Deployment prerequisites](prerequisites.md).

## 1. Start the artifact retention worker

The retention worker is installed as `run_artifact_retention.py` in the selected CAESAR-REST Python environment.

For example:

```bash
/opt/caesar-rest/venv/bin/run_artifact_retention.py \
	--dbhost=127.0.0.1 \
	--dbport=27017 \
	--dbname=caesardb \
	--retention-root=/storage/caesar-rest/pipeline-artifacts \
	--poll-seconds=30
```

Replace the Python environment, MongoDB connection options and retention directory with the values configured for your deployment.

The retention root must be an absolute, normalized path, different from `/`, and must be writable by the retention worker. The polling interval and retention limits must be positive.

The REST application, job monitor and retention worker must access the same MongoDB database. The REST application and worker must also agree on the application-side artifact retention root.

### Shared storage across REST and Slurm hosts

When the REST application and Slurm execution nodes run on separate machines, the same retained artifacts may be accessible through different filesystem mount paths.

For example:

| Component | Artifact retention root |
| --- | --- |
| REST application and retention worker | `/storage/caesar-rest/pipeline-artifacts` |
| Slurm execution nodes | `/cluster-storage/caesar-rest/pipeline-artifacts` |

Configure the REST application using:

```bash
--pipeline_artifact_retention_root=/storage/caesar-rest/pipeline-artifacts
--pipeline_artifact_retention_root_cluster=/cluster-storage/caesar-rest/pipeline-artifacts
```

Configure the standalone worker using the application-side path:

```bash
--retention-root=/storage/caesar-rest/pipeline-artifacts
```

Both paths must reference the same underlying persistent storage. Ensure that the REST service account, worker and Slurm execution identities have the necessary filesystem permissions.

See [Deployment prerequisites](prerequisites.md) for shared filesystem requirements, mount-path mapping and UID/GID considerations.

### Worker configuration

The retention worker accepts the following command-line options:

| Option | Description | Default |
|--------|-------------|---------|
| `--dbhost` | MongoDB hostname | `localhost` |
| `--dbport` | MongoDB port | `27017` |
| `--dbname` | MongoDB database name | `caesardb` |
| `--retention-root` | Absolute directory for persistent artifacts | Required |
| `--poll-seconds` | Polling interval in seconds | `30` |
| `--max-file-bytes` | Maximum size of an individual artifact file | `1073741824` (1 GiB) |
| `--max-directory-bytes` | Maximum size of a retained artifact directory | `1099511627776` (1 TiB) |
| `--max-directory-entries` | Maximum entries in a retained directory | `100000` |
| `--max-directory-depth` | Maximum artifact directory depth | `16` |

Size and directory limits should be configured according to
the requirements of the scientific applications being executed.

For example, radio-interferometric measurement sets can require
significant storage capacity and may contain many files.

## 2. Run the worker with systemd

For production deployments, run the retention worker as a dedicated systemd service.

Create `/etc/systemd/system/caesar-rest-artifact-retention.service`:

```ini
[Unit]
Description=CAESAR-REST pipeline artifact retention worker
After=network.target mongod.service
RequiresMountsFor=/storage/caesar-rest/pipeline-artifacts

[Service]
Type=simple
User=caesar
Group=caesar
WorkingDirectory=/opt/caesar-rest
ExecStart=/opt/caesar-rest/venv/bin/run_artifact_retention.py --dbhost=127.0.0.1 --dbport=27017 --dbname=caesardb --retention-root=/storage/caesar-rest/pipeline-artifacts --poll-seconds=30
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Adapt the service account, installation directory, database connection and retention root to your deployment.

`RequiresMountsFor=` establishes dependencies on the mounts required to access the retention directory. It does not replace verification that shared storage is available and writable.

Enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now caesar-rest-artifact-retention.service
sudo systemctl status caesar-rest-artifact-retention.service
```

Inspect worker logs:

```bash
sudo journalctl -u caesar-rest-artifact-retention.service -n 100 --no-pager
```

Restart the service after modifying its configuration:

```bash
sudo systemctl restart caesar-rest-artifact-retention.service
```

For an initial deployment, run a single worker instance to avoid unnecessary contention. The retention implementation includes concurrency protections, but a single worker is the recommended starting configuration.

## 3. Retention processing

The worker periodically queries MongoDB for eligible runs.

A run is eligible when:

- Its scientific status is `COMPLETED`.
- Its output artifacts have been registered.
- At least one artifact is registered.
- No retained artifact list has been published.
- Its retention status is absent or `PENDING`.

The worker atomically marks an eligible run as `COPYING` before
processing it.

Artifact promotion includes integrity checks. The retained
artifacts are published only after successful promotion.

On success, the run receives:

`retention_status = READY`

On failure, the worker records:

`retention_status = FAILED`

and stores diagnostic information in the run metadata.

Failed retention operations require investigation and recovery;
the worker does not automatically repeat failed copying operations.

A retention failure does not necessarily indicate that the scientific job failed. The scientific execution status and artifact retention status are maintained separately. A failed retention operation must be investigated before retrying; the worker does not automatically reset `FAILED` runs to `PENDING`. Likewise, a worker interruption can leave a run in `COPYING`, which is not automatically reclaimed by the worker's normal eligibility query. Recovery must follow a controlled administrative procedure after checking MongoDB state, retained files and possible concurrent workers. Do not manually change retention states without verifying these conditions.

## 4. Monitoring artifact readiness

Clients can inspect the retention state using:

`GET /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}`

A successfully completed and retained run reports:

```json
{
  "status": "COMPLETED",
  "artifacts_status": "READY",
  "readiness": {
    "can_select": true,
    "can_consume": true
  }
}
```

A scientifically completed run may not immediately report
`can_consume = true`, because artifact registration and retention
are performed independently of scientific execution.

For agent-driven workflows such as MAASAI, downstream run
registration should be attempted only when the required
upstream artifacts are available. The artifact-binding layer
performs the authoritative integrity verification.

See the [Pipeline API reference](../api/scientific-pipelines.md)
for further details.

## 5. Administrative artifact reconciliation

The normal artifact-retention worker promotes registered outputs of
completed scientific pipeline runs.

Once a run has a published `retained_artifacts` list, the worker does not
automatically discover and append additional artifacts.

This behavior protects existing artifact indices and prevents ordinary
retention processing from modifying an already published artifact set.

However, a previously completed run may contain additional scientific
diagnostics that were not registered because its output contract was updated
after execution.

CAESAR-REST provides an explicit administrative reconciliation utility for
recovering such missing regular-file artifacts without rerunning the
scientific application.

### Reconciliation scope

The utility is:

```text
scripts/reconcile_pipeline_artifacts.py
```

It supports previously completed and fully retained Pipeline V2 runs.

The reconciliation implementation:

- Verifies the run identity, successful execution state and existing
  retention metadata.
- Uses the current application output contract to rediscover artifacts
  in the original job workspace.
- Preserves all existing artifact indices and retention records.
- Appends only newly discovered regular-file artifacts.
- Copies and checksums newly registered files.
- Checks existing retained directory manifests without copying the
  scientific directories again.
- Serializes reconciliation with mixed-artifact retention using the
  existing per-run retention lock.
- Atomically publishes the expanded artifact registration and retention
  arrays after successful copying.
- Supports safe retry after interruption by verifying prepared files
  before reuse.

The utility deliberately refuses to append new directory artifacts.

Existing retained scientific directories are not recopied.

### Dry run

Run the utility in the configured CAESAR-REST Python environment with
the normal MongoDB settings.

Example:

```bash
python scripts/reconcile_pipeline_artifacts.py \
	--pipeline-id PIPELINE_ID \
	--node-id NODE_ID \
	--run-id RUN_ID \
	--retention-root /storage/caesar-rest/pipeline-artifacts
```

The command defaults to dry-run mode.

A dry run verifies the existing retention state, discovers available
additional artifacts and reports the proposed changes.

It does not copy new artifacts or update MongoDB.

The output includes:

```json
{
  "run_id": "RUN_ID",
  "existing": 58,
  "additional": 0,
  "total": 58,
  "dry_run": true,
  "new_artifacts": []
}
```

The example counts are illustrative. In a real response, `new_artifacts`
contains the proposed indices, logical names and relative paths of the
newly discovered artifacts.

### Apply reconciliation

After reviewing the dry-run results, use the same command with `--apply`:

```bash
python scripts/reconcile_pipeline_artifacts.py \
	--pipeline-id PIPELINE_ID \
	--node-id NODE_ID \
	--run-id RUN_ID \
	--retention-root /storage/caesar-rest/pipeline-artifacts \
	--apply
```

The operation requires access to the original job workspace and persistent
retention storage.

Run it only in a trusted administrative environment. Ensure that the
scientific job is no longer writing outputs.

The utility is an offline administrative operation, not a public REST
endpoint.

On successful application, it reports `committed: true`.

### Verify reconciliation

After applying reconciliation:

1. Retrieve the run status and verify that the artifact inventory has
   the expected size.
2. Confirm that `artifacts_status` is `READY` and
   `readiness.can_consume` is `true`.
3. Retrieve the artifact inventory through the public REST API.
4. Download representative newly registered files and verify their
   contents.
5. Repeat the reconciliation in dry-run mode and confirm that
   `additional` is zero.

Reconciliation preserves previously registered artifact indices.
It does not rerun scientific processing, regenerate job archives or
modify preferred-run selection.

### Limitations and safety

Reconciliation should not be treated as automatic output-contract migration
for every historical run.

The operation requires the original workspace to remain available, with
newly discovered files matching their registered metadata.

Existing retained directory manifests are validated, but this
administrative operation does not perform full byte-level rehashing of
all retained scientific directories.

Do not use reconciliation to repair corrupted retained data or incomplete
scientific execution. Such cases require separate investigation.

The ordinary `/pipelines/{pipeline_id}/sync` endpoint synchronizes
execution state; it does not append missing artifacts to an already
retained run.

## 6. Historical Pipeline V2 archive migration

Existing staged Pipeline V2 jobs may still have full job-output archives
created before lightweight diagnostic archive policies were introduced.

CAESAR-REST provides an administrative migration utility:

```text
scripts/migrate_pipeline_job_archives.py
```

The utility can replace selected historical archives with lightweight
diagnostic archives without rerunning scientific processing.

It requires a successful staged Pipeline V2 job, a completed pipeline run,
a complete registered and retained artifact set, the original workspace,
and a valid application archive policy.

### Dry run

```bash
python scripts/migrate_pipeline_job_archives.py \
	--owner OWNER_ID \
	--retention-root /storage/caesar-rest/pipeline-artifacts \
	--job-id JOB_ID
```

The command validates eligibility but does not create or modify archives.

Multiple `--job-id` arguments may be supplied to inspect multiple jobs.

### Apply

Append `--apply` only after reviewing the dry-run results:

```bash
python scripts/migrate_pipeline_job_archives.py \
	--owner OWNER_ID \
	--retention-root /storage/caesar-rest/pipeline-artifacts \
	--job-id JOB_ID \
	--apply
```

For each eligible job, the utility:

1. Verifies the job and run records.
2. Verifies retained file checksums and directory manifests.
3. Generates a separate diagnostic archive using the current
   application archive policy.
4. Validates archive contents against the original files.
5. Refuses replacement if diagnostic files were omitted by policy
   size or count limits.
6. Atomically replaces the original archive when the new archive
   is smaller and validation succeeds.

The migration does not modify MongoDB artifact records or pipeline
selections.

The existing `/job/{job_id}/output` endpoint continues to reference
the same archive filename.

### Operational precautions

Run archive migration only when the job monitor is not writing the selected
archives and no clients are downloading them.

The tool does not coordinate archive replacement with active readers
or writers.

The retention directory and original job workspace are separate storage
resources. Archive migration may substantially reduce archive storage,
but it does not remove scientific files from the job workspace.

Do not delete original scientific workspaces solely because archive
migration succeeded.

For archive format and policy details, see the
[Jobs REST API](../api/jobs.md).

