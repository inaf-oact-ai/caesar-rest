# Accounting service (legacy / limited support)

> **Legacy functionality — limited support:** CAESAR-REST retains an accounting service inherited from earlier NEANIAS deployments. Its basic data-storage and job-usage statistics remain implemented, but the service has not been fully modernized or validated against the current Slurm and Pipeline V2 deployment architecture. It is not required for normal job execution, job monitoring or pipeline artifact retention.

## 1. Overview

The CAESAR-REST accounting service periodically collects statistics about user data storage and submitted jobs and stores the resulting information in MongoDB.

The service is implemented in:

- `apps/run_accounter.py`: Standalone polling process.
- `caesar_rest/accounter.py`: Accounting calculations and MongoDB updates.
- `caesar_rest/accounting_route.py`: REST endpoints for retrieving accounting information.

The accounting worker operates independently of the REST web application and the Slurm job monitoring service.

### Collected information

The existing implementation calculates:

| Category | Information |
| --- | --- |
| Users | Number of users discovered through the configured filesystem directories |
| Data storage | Per-user uploaded-data directory size |
| Job storage | Per-user job directory size |
| Jobs | Total number of recorded jobs |
| Job states | Pending, running, completed, failed, aborted and unknown job counts |
| Runtime | Aggregated job elapsed time and completed-job elapsed time |
| Application statistics | Aggregated storage usage, job counts and runtime information across discovered users |

Accounting information is stored in the configured MongoDB database:

- `<username>.accounting`: Statistics for an individual user.
- `appstats`: Aggregated statistics for the application.

The worker updates existing accounting documents rather than creating an independent historical time series for every polling cycle.

These statistics are derived from filesystem directories and CAESAR-REST job records. They are not authoritative Slurm resource accounting or billing records.

## 2. Implementation status and limitations

The accounting service remains available in the source tree, but several aspects reflect its original deployment architecture.

### Legacy Celery compatibility

The accounting module retains a historical Celery task for compatibility with earlier deployments. Task registration is optional: when Celery is not installed, the standalone accounting function remains importable and can be invoked directly by `run_accounter.py`.

The standalone service therefore does not require the optional Celery dependency. Nevertheless, its accounting algorithms and deployment behavior have not been fully validated against the current Slurm and Pipeline V2 architecture.

### Filesystem-based accounting

The service discovers users by scanning the subdirectories of the configured data and job storage roots.

It then calculates directory sizes and queries the corresponding per-user MongoDB job collections.

This approach has limitations:

- Registered users without corresponding filesystem directories may not be included.
- Full directory scans may be expensive on large shared filesystems.
- Retained Pipeline V2 artifacts are not included as a separate storage category.
- Usage recorded in other storage backends may not be represented.
- The implementation does not provide comprehensive Slurm CPU, memory, GPU or allocated-resource accounting.

The worker uses the external `du` utility for filesystem-size calculations. Its output and behavior depend on the execution environment and accessible filesystems.

### Maintenance status

The existing service should be considered a legacy utility with limited support.

Its basic algorithms remain implemented, but it has not undergone the same modernization and integration testing as the REST application, Slurm job monitor or Pipeline V2 artifact retention worker.

For current production deployments, the accounting service is optional and should not be enabled without additional validation.

## 3. Historical standalone execution

The existing launcher accepts command-line arguments and runs a continuous accounting loop.

The following example illustrates its intended invocation:

```bash
/opt/caesar-rest/venv/bin/run_accounter.py \
	--datadir=/storage/caesar-rest/data \
	--jobdir=/storage/caesar-rest/jobs \
	--dbhost=127.0.0.1 \
	--dbport=27017 \
	--dbname=caesardb \
	--job_monitoring_period=300
```

**Compatibility note**: This example documents the current command-line interface; it is not a validated production startup command. The standalone accounting service no longer requires Celery to be installed. However, its filesystem accounting, MongoDB interactions and compatibility with modern job records must still be validated before production deployment.

The example uses a five-minute polling interval rather than the historical 30-second default to reduce the frequency of filesystem scans. The appropriate interval depends on the storage size and operational requirements.

### Command-line options

The standalone launcher currently recognizes:

| Option | Description | Default |
| --- | --- | --- |
| `--datadir` | Root directory containing user data | `/opt/caesar-rest/data` |
| `--jobdir` | Root directory containing user job files | `/opt/caesar-rest/jobs` |
| `--job_monitoring_period` | Time between accounting scans, in seconds | `30` |
| `--dbname` | MongoDB database name | `caesardb` |
| `--dbhost` | MongoDB hostname | `localhost` |
| `--dbport` | MongoDB port | `27017` |
| `--mount_rclone_volume` | Historical rclone mount flag | Disabled |
| `--mount_volume_path` | Historical container mount path | `/mnt/storage` |
| `--rclone_storage_name` | Historical rclone remote name | `neanias-nextcloud` |
| `--rclone_storage_path` | Historical rclone remote path | `.` |

The rclone-related arguments are retained by the parser but are not used by the standalone accounting loop. They should not be interpreted as enabling automatic remote-storage accounting.

The configured data and job directories must be accessible to the account running the service, and the MongoDB connection must permit reading job metadata and writing accounting information.

## 4. Accounting REST endpoints

The CAESAR-REST application retains two accounting endpoints.

### User accounting

```http
GET /caesar/api/v1.0/accounting
```

Returns the accounting record associated with the authenticated user's storage identity, when available.

### Application statistics

```http
GET /caesar/api/v1.0/appstats
```

Returns the aggregated application statistics stored in MongoDB, when available.

Both endpoints use the existing CAESAR-REST authentication decorator.

The application statistics endpoint is based on aggregated MongoDB information and should not be assumed to enforce administrative access merely because it exposes application-wide data. Review the authorization policy before exposing it in a multi-user deployment.

These endpoints read information previously generated by the accounting worker. They do not automatically execute a fresh accounting scan when requested.

If the worker is not running, the endpoints may return missing or stale statistics.

## 5. Historical deployment alternatives

Earlier CAESAR-REST deployments also referenced the Docker image [`sriggi/caesar-rest-accounter:latest`](https://hub.docker.com/r/sriggi/caesar-rest-accounter), intended for Docker Compose or Kubernetes deployments.

This container belongs to the historical NEANIAS deployment model. Its compatibility with the current CAESAR-REST codebase, Python environment and execution infrastructure has not been revalidated.

It should be treated as an archival reference rather than a recommended deployment method.

## 6. Recommendations for modern deployments

For the current Slurm and Pipeline V2 architecture, the accounting service is **not required** for:

- Scientific job submission and execution.
- Slurm job-state monitoring.
- Pipeline run-state synchronization.
- Artifact registration.
- Persistent artifact retention.
- Downstream pipeline-stage execution.

These responsibilities are handled by the main REST application, the [job monitoring service](job-monitoring.md) and the [artifact retention worker](artifact-retention.md).

If accounting functionality is required in the future, the recommended approach is to modernize the service separately, beginning with a review of authentication and authorization, the accounting data model, filesystem scanning performance and integration tests against the current MongoDB schema. The unnecessary standalone Celery dependency has already been removed.

A future accounting implementation could distinguish data uploads, job working directories, retained pipeline artifacts and Slurm resource usage. Such capabilities should not be attributed to the existing implementation.

Until that modernization is completed, the accounting service should remain an optional legacy component.

## References

- [Deployment overview](index.md)
- [Deployment prerequisites](prerequisites.md)
- [Job monitoring](job-monitoring.md)
- [Pipeline artifact retention](artifact-retention.md)
- [Slurm deployment](slurm.md)
- [Legacy Celery deployment](celery.md)
- [Archived original README](../archive/ORIGINAL_README.md)
