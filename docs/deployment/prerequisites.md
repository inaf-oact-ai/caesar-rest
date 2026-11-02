# Deployment prerequisites and shared services

This guide describes the shared infrastructure and filesystem preparation required before running CAESAR-REST services. It covers the application service account, working directories, persistent storage, MongoDB and optional log forwarding.

The examples assume a Linux host with a dedicated application account and use `/storage/caesar-rest` as an illustrative persistent storage root. The CAESAR-REST Python environment, launcher scripts and runtime socket may reside elsewhere on the application host. Adapt paths, ownership, service names and storage configuration to your deployment.

Install the CAESAR-REST Python package according to the [installation guide](../installation.md). Configure the REST web service, job execution backend, job monitor and artifact retention worker using their respective [deployment guides](index.md).

CAESAR-REST requires MongoDB and one configured execution backend. Slurm is the recommended backend; Kubernetes is an alternative, while Celery is retained as a legacy backend. The external scheduler infrastructure must be configured separately.

## 1. Prepare the application host

### Create a dedicated service account

For a production deployment, use a dedicated operating-system account to run the CAESAR-REST application and related services.

For example, on Ubuntu:

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin caesar
```

If the `caesar` account already exists, do not recreate or modify it unnecessarily. The account must have the permissions required by the selected scheduler and application services.

The examples below assume that the service account and group are both named `caesar`.

### Create the application directories

CAESAR-REST uses separate directories for uploaded data, job outputs, scientific models, logs, runtime files and persistent pipeline artifacts. In deployments where the REST application and the Slurm execution nodes run on different machines, directories containing data required by scientific jobs must be available to both environments through a shared filesystem or an explicitly configured staging mechanism. Local runtime directories do not generally require shared storage.

The following layout is illustrative:

```text
/storage/caesar-rest/
    data/
    jobs/
    models/
    logs/
    run/
    pipeline-artifacts/
```

Create the directories:

```bash
sudo install -d -o caesar -g caesar -m 0750 /storage/caesar-rest
sudo install -d -o caesar -g caesar -m 0750 \
    /storage/caesar-rest/data \
    /storage/caesar-rest/jobs \
    /storage/caesar-rest/models \
    /storage/caesar-rest/logs \
    /storage/caesar-rest/run \
    /storage/caesar-rest/pipeline-artifacts
```

In distributed deployments, create shared directories on the mounted storage filesystem and local runtime directories on the appropriate service host. Do not assume that `/storage/caesar-rest` is automatically shared merely because of its path: it must refer to an actual shared filesystem mounted on the required machines. When using NFS or another shared filesystem, configure ownership and permissions according to the filesystem's identity-mapping and access-control policies.

The directory roles are:

| Directory | Purpose |
| --- | --- |
| `data/` | Uploaded application data and locally managed datasets |
| `jobs/` | Job outputs and execution-related files |
| `models/` | Scientific models and associated weights |
| `logs/` | Optional application and service log files |
| `run/` | Runtime files, including the uWSGI Unix socket |
| `pipeline-artifacts/` | Persistent retained outputs of scientific pipeline stages |

These paths are examples rather than mandatory defaults. Configure the application and worker services to use the actual directories selected for the deployment.

The `data/`, `jobs/` and `models/` directories should be accessible to the REST application and to the Slurm execution nodes that consume or produce their contents. The `pipeline-artifacts/` directory must additionally be accessible to the artifact retention worker and the downstream pipeline staging environment. The `logs/` directory may remain local if centralized log collection is used, while `run/` should normally remain local to the web application host because it contains the uWSGI Unix socket.

For the web application, the runtime socket directory must also be accessible to the Nginx worker as described in [Web application deployment](web-application.md).

### Configure persistent storage

Application data, job outputs and retained scientific pipeline artifacts should reside on persistent storage appropriate for the expected workload.

For deployments where CAESAR-REST and the Slurm execution nodes run on different machines, the directories used by scientific jobs must be accessible from both environments. A shared filesystem, such as NFS or a distributed filesystem, is a common solution. Alternatively, an explicit data staging mechanism may be used, provided that all required files are transferred to the correct execution environment.

For a shared-filesystem deployment, the following practices are recommended:

- **Consistent mount paths:** Prefer mounting shared directories at the same absolute paths on the REST host and Slurm execution nodes. This simplifies job submission, container bind mounts and artifact staging.
- **Appropriate permissions:** Ensure that the CAESAR-REST service account, Slurm job execution identities and retention worker have the required read, write and directory traversal permissions. For shared POSIX filesystems, coordinate numeric user/group IDs or use an appropriate ACL strategy.
- **Persistent availability:** Shared storage must be mounted and available before services or scientific jobs that depend on it are started.
- **Storage capacity:** Size storage for expected input datasets, job outputs, scientific models and retained artifacts, including potentially large radio-interferometric measurement sets.
- **Container visibility:** When scientific applications execute inside Singularity/Apptainer containers, ensure that the required host directories are correctly exposed through container bind mounts.

The `data/`, `jobs/` and `models/` directories should be accessible wherever the corresponding scientific jobs read or write files.

For staged scientific pipelines, the artifact retention directory must be persistent and accessible to the REST application, artifact retention worker and downstream staging environment. All participating components must agree on the configured artifact locations.

Artifact retention is required for multi-stage Pipeline V2 workflows because downstream stages consume retained outputs from preceding stages rather than arbitrary files from previous job working directories.

See [Pipeline artifact retention](artifact-retention.md) for the complete lifecycle and worker configuration, and [Slurm deployment](slurm.md) for scheduler configuration.

### Optional external storage mounts

External storage can be mounted before starting CAESAR-REST. For example, some deployments use Rclone to expose remote storage through a local filesystem mount.

Rclone configuration is deployment-specific and is not required for installations using ordinary local or shared filesystems.

If using Rclone, configure the remote credentials securely, select appropriate filesystem permissions and ensure that the mount is available before the application or job services access it. Avoid globally writable mount configurations unless explicitly required and reviewed.

The [application CLI reference](../reference/cli-options.md) documents the available application configuration options.

## 2. Configure MongoDB

CAESAR-REST requires MongoDB to persist application metadata, user and job information, dataset registry records and scientific pipeline execution state.

Install and configure a supported MongoDB deployment using the official MongoDB documentation and your organization's database administration policies.

For a local MongoDB installation managed by systemd, verify the actual service name. On installations using `mongod.service`, start and enable the service with:

```bash
sudo systemctl enable --now mongod.service
sudo systemctl status mongod.service
```

The service name may differ depending on how MongoDB was installed.

For a local database listening on the default MongoDB port, the corresponding CAESAR-REST application options are:

```bash
--db --dbhost=127.0.0.1 --dbport=27017 --dbname=caesardb
```

These options belong to the CAESAR-REST application configuration, not to the MongoDB server configuration.

For the Bash launcher described in [Web application deployment](web-application.md), they are included in the application's `PYARGS` variable.

### Database persistence and security

MongoDB must retain its data across service restarts and host maintenance.

For production deployments:

- Use persistent database storage and maintain a tested backup and recovery procedure.
- Restrict database network access to the CAESAR-REST components and authorized administrators.
- Configure database authentication and transport encryption according to the site's security requirements.
- Do not expose an unauthenticated MongoDB instance to untrusted networks.
- Ensure that the REST application, job monitor and artifact retention worker use the intended MongoDB database.

MongoDB can also be deployed using containers or an independently managed database service. Container volumes, authentication, network configuration and backup procedures must be configured for the selected deployment.

Historical MongoDB container examples from the original README should not be assumed to represent a validated production configuration.

## 3. Optional log forwarding with Filebeat

CAESAR-REST can write application logs to files for local inspection or forwarding to a centralized logging system.

Filebeat is an optional external service that can collect and forward log files to an Elasticsearch-compatible logging infrastructure. It is not required for CAESAR-REST operation.

When Filebeat is installed and configured as a systemd service, start it with:

```bash
sudo systemctl enable --now filebeat.service
sudo systemctl status filebeat.service
```

Configure Filebeat separately to read the appropriate CAESAR-REST log files and forward them to the intended destination.

Ensure that the Filebeat process has sufficient permission to read the selected logs without unnecessarily granting access to application secrets or protected data.

If centralized log forwarding is not required, CAESAR-REST can continue to use its normal application logging mechanisms.

## 4. Verify the prerequisites

Before starting the REST application and related workers, verify that:

1. The dedicated application account exists and has appropriate filesystem permissions.
2. The configured data, job, model and runtime directories exist.
3. For distributed Slurm deployments, confirm that all required shared directories are mounted and accessible on the REST host and execution nodes, preferably using consistent absolute paths. Verify actual read/write permissions using the service and job execution identities.
4. MongoDB is running and accessible from the application environment.
5. The selected execution backend has been configured and its required services are available.
6. Persistent artifact storage is available when running staged scientific pipelines.
7. Optional external storage mounts and log-forwarding services are functioning if enabled.

After completing these checks, proceed with [Web application deployment](web-application.md), [Job monitoring](job-monitoring.md) and, when required, [Pipeline artifact retention](artifact-retention.md).

For Slurm-based execution, consult the dedicated [Slurm deployment guide](slurm.md).

## References

- [CAESAR-REST installation](../installation.md)
- [Deployment overview](index.md)
- [Web application deployment](web-application.md)
- [Slurm deployment](slurm.md)
- [Pipeline artifact retention](artifact-retention.md)
- [MongoDB documentation](https://www.mongodb.com/docs/)
- [Filebeat documentation](https://www.elastic.co/docs/reference/beats/filebeat/)
- [Rclone documentation](https://rclone.org/docs/)
