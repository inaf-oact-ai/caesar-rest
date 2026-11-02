# Job monitoring service

The CAESAR-REST job monitoring service tracks scientific jobs submitted to the configured execution backend and updates their execution state in MongoDB.

The service runs independently of the REST web application and periodically queries the scheduler for changes in job status. It also synchronizes associated scientific pipeline runs and registers output artifacts when pipeline execution completes successfully.

For multi-stage Pipeline V2 workflows, registered artifacts must subsequently be retained in persistent storage before downstream stages can consume them.

Artifact retention can be performed by a separate retention worker or, when explicitly configured, automatically by the job monitoring service. See [Pipeline artifact retention](artifact-retention.md) for the retention lifecycle and storage requirements.

The monitor currently supports Slurm and Kubernetes. **Slurm is the default and recommended backend.** Celery jobs use a different, legacy monitoring mechanism and are not processed by this standalone monitoring service.

Before starting the monitor, ensure that CAESAR-REST is installed, MongoDB is available and the corresponding execution backend is configured. See [Installation](../installation.md), [Deployment prerequisites](prerequisites.md) and [Slurm deployment](slurm.md).

## 1. Start the job monitoring service

The job monitor is installed as `run_jobmonitor.py` in the selected Python environment.

For a Slurm deployment, start the monitor using the following example:

```bash
/opt/caesar-rest/venv/bin/run_jobmonitor.py \
	--job_scheduler=slurm \
	--job_monitoring_period=30 \
	--dbhost=127.0.0.1 \
	--dbport=27017 \
	--dbname=caesardb \
	--slurm_host=SLURM_HOSTNAME \
	--slurm_port=6820 \
	--slurm_user=caesar \
	--slurm_keyfile=/SECURE/PATH/slurm_jwt_hs256.key
```

Replace the virtual environment path, Slurm hostname, execution identity and JWT key path with the values configured for your deployment.

The monitor must use the same MongoDB database and scheduler infrastructure as the REST application. The Slurm user must be authorized to inspect submitted jobs, and the JWT signing key must be protected against unauthorized access.

### Command-line options

The following options are supported by `apps/run_jobmonitor.py`.

| Option | Description | Default |
| --- | --- | --- |
| `--job_scheduler` | Execution backend: `slurm` or `kubernetes` | `slurm` |
| `--job_monitoring_period` | Polling interval in seconds | `30` |
| `--dbhost` | MongoDB hostname | `localhost` |
| `--dbport` | MongoDB port | `27017` |
| `--dbname` | MongoDB database name | `caesardb` |
| `--slurm_host` | Slurm REST service hostname or IP address | `SLURM_HOST` placeholder |
| `--slurm_port` | Slurm REST service port | `6820` |
| `--slurm_user` | Slurm identity used by the REST client | `cirasa` |
| `--slurm_keyfile` | Slurm JWT signing key file | Empty |
| `--kube_incluster` | Use Kubernetes in-cluster configuration | Disabled |
| `--kube_config` | Kubernetes configuration file | Empty; standard configuration may be used |
| `--kube_cafile` | Kubernetes CA certificate file | Empty |
| `--kube_keyfile` | Kubernetes client private key file | Empty |
| `--kube_certfile` | Kubernetes client certificate file | Empty |
| `--loglevel` | Application log level | `INFO` |
| `--logtofile` | Enable file logging | Disabled |
| `--logdir` | Log directory | `/opt/caesar-rest/logs` |
| `--logfile` | Log filename | `app_logs.json` |
| `--logfile_maxsize` | Rotating log size in MB | `5` |

The monitor also accepts artifact retention options, documented in Section 3.

For Kubernetes deployments, select `--job_scheduler=kubernetes` and supply the appropriate Kubernetes connection and certificate options. The required Python integration and external Kubernetes infrastructure must be installed and configured separately.

For Slurm, the REST endpoint must support the scheduler and accounting queries required to recover job statuses. See [Slurm deployment](slurm.md).

## 2. Run the monitor with systemd

For a production deployment, run the job monitor as a systemd service using a dedicated application account.

Create `/etc/systemd/system/caesar-rest-jobmonitor.service`:

```ini
[Unit]
Description=CAESAR-REST job monitoring service
After=network.target mongod.service

[Service]
Type=simple
User=caesar
Group=caesar
WorkingDirectory=/opt/caesar-rest
ExecStart=/opt/caesar-rest/venv/bin/run_jobmonitor.py --job_scheduler=slurm --job_monitoring_period=30 --dbhost=127.0.0.1 --dbport=27017 --dbname=caesardb --slurm_host=SLURM_HOSTNAME --slurm_port=6820 --slurm_user=caesar --slurm_keyfile=/SECURE/PATH/slurm_jwt_hs256.key
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Adapt the installation paths and command-line arguments to your environment. The example assumes a local MongoDB instance and access to a separately configured Slurm REST service.

After creating the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now caesar-rest-jobmonitor.service
sudo systemctl status caesar-rest-jobmonitor.service
```

Inspect the service logs with:

```bash
sudo journalctl -u caesar-rest-jobmonitor.service -n 100 --no-pager
```

Following subsequent configuration changes, restart the service:

```bash
sudo systemctl restart caesar-rest-jobmonitor.service
```

The `After=` directive establishes startup ordering but does not guarantee that MongoDB or Slurm is ready. If the monitor depends on remote services or network-mounted storage, configure suitable startup dependencies and availability checks.

The monitoring process runs continuously, sleeping for the configured interval between monitoring cycles.

## 3. Pipeline artifact registration and retention

When the job monitor detects a completed scientific pipeline job, CAESAR-REST synchronizes the corresponding pipeline execution state and attempts to register its output artifacts.

Artifact registration records the outputs needed for subsequent processing, including their metadata and integrity information.

Artifact registration and artifact retention are distinct operations. Registration does not by itself guarantee that artifacts have been copied into persistent retention storage.

### Retention using the standalone worker

A dedicated artifact retention worker can independently process completed pipeline runs whose outputs have been registered.

This separates job-status monitoring from artifact promotion and is suitable for deployments that manage retention as a separate system service.

See [Pipeline artifact retention](artifact-retention.md).

### Automatic retention in the job monitor

The current job monitoring implementation also supports automatic retention of completed pipeline outputs.

To enable this mode, configure an application-side retention root:

```bash
--pipeline_artifact_retention_root=/storage/caesar-rest/pipeline-artifacts
```

The monitor accepts the following additional options:

| Option | Description | Default |
| --- | --- | --- |
| `--pipeline_artifact_retention_root` | Persistent artifact storage root | Empty; automatic retention disabled |
| `--pipeline_artifact_retention_max_file_bytes` | Maximum size of an artifact file | 1 GiB |
| `--pipeline_artifact_retention_max_directory_bytes` | Maximum retained directory size | 1 TiB |
| `--pipeline_artifact_retention_max_directory_entries` | Maximum directory entries | `100000` |
| `--pipeline_artifact_retention_max_directory_depth` | Maximum directory nesting depth | `16` |

When the retention root is configured, the monitor attempts to retain eligible completed pipeline artifacts using the supplied storage limits.

The retention root must be an absolute, normalized path and must be accessible and writable by the monitoring service account.

When the REST server and Slurm execution nodes have different mount paths, the monitor uses the **application-side** retention root. Slurm execution and downstream pipeline staging use the corresponding cluster-side path configured in the REST application.

For example:

- Application-side retention root: `/storage/caesar-rest/pipeline-artifacts`
- Cluster-side retention root: `/cluster-storage/caesar-rest/pipeline-artifacts`

The two locations must refer to the same underlying persistent storage.

For a new deployment, select a clear retention operating model. If using the standalone worker, automatic retention in the job monitor can remain disabled. Avoid configuring overlapping retention services without understanding their coordination and recovery behavior.

Artifact retention failures must be investigated independently of the scientific job's execution status.

## 4. Verify job monitoring

After starting the service, perform the following checks:

1. Confirm that the job monitor systemd unit is active and that the monitoring loop is running without repeated initialization errors.
2. Verify that the monitor can connect to the intended MongoDB database and configured scheduler.
3. Submit a small test job through CAESAR-REST and verify that its state progresses through the expected scheduler states.
4. Confirm that the job's final state is updated in MongoDB after scheduler completion.
5. For scientific pipelines, verify that the corresponding pipeline run reaches its expected terminal state and that successful output artifacts are registered.
6. If automatic retention or a standalone retention worker is enabled, verify that retained artifacts reach the expected ready state and remain available for downstream processing.

The monitor's polling interval affects how quickly completed jobs are reflected in MongoDB.

A successful scheduler submission does not by itself validate job monitoring, artifact registration or persistent retention. Verify these operations separately.

For troubleshooting, inspect the job monitor logs and the corresponding Slurm REST service logs. See [Slurm deployment](slurm.md) and [Pipeline artifact retention](artifact-retention.md).

## References

- [CAESAR-REST installation](../installation.md)
- [Deployment prerequisites](prerequisites.md)
- [Slurm deployment](slurm.md)
- [Pipeline artifact retention](artifact-retention.md)
- [Application CLI reference](../reference/cli-options.md)
- [Original README deployment instructions](../archive/ORIGINAL_README.md)
