# Pipeline artifact retention

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 1006–1142). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

### **Run pipeline artifact retention service**

CAESAR-REST provides a standalone artifact retention worker responsible
for preserving the outputs of completed scientific pipeline runs.

The service is implemented in `apps/run_artifact_retention.py` and runs
independently of the REST application and job monitoring service.

The pipeline artifact lifecycle consists of three main steps:

1. The scientific job completes successfully and its pipeline run
   transitions to `COMPLETED`.
2. The output artifacts are registered in MongoDB, including their
   names, types, sizes and integrity metadata.
3. The artifact retention worker copies and verifies registered
   artifacts into the configured persistent retention storage.

The retention worker processes completed, registered pipeline runs
whose artifacts have not yet been retained.

**For multi-stage Pipeline V2 execution, artifact retention is
required:** downstream stages consume retained upstream artifacts,
not arbitrary files from the original job working directory.

#### Starting the retention worker

After installing CAESAR-REST, start the service with:

```bash
$INSTALL_DIR/bin/run_artifact_retention.py \
  --dbhost=localhost \
  --dbport=27017 \
  --dbname=caesardb \
  --retention-root=/opt/caesar-rest/pipeline-artifacts \
  --poll-seconds=30
```

Replace the retention root with the absolute path configured for
your installation.

The retention root must be accessible and writable by the
retention worker. It must also be accessible to the REST service
and to the staging environment used for downstream pipeline runs.

The REST application and retention worker must be configured to
use the same MongoDB database and artifact retention storage.

#### Worker configuration

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

#### Retention processing

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

For an initial deployment, run exactly one retention worker
instance. The existing per-run filesystem locking mechanism
provides additional protection, but a single worker is the
recommended initial configuration.

#### Monitoring artifact readiness

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

See the [Pipeline V2 API reference](docs/pipeline_v2_api.md)
for further details.

   
