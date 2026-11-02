# Job monitoring service

The CAESAR-REST job monitoring service tracks scientific jobs submitted to the configured execution backend and updates their execution state in MongoDB.

The service runs independently of the REST web application and periodically queries the scheduler for changes in job status. It also synchronizes associated scientific pipeline runs and registers output artifacts when pipeline execution completes successfully.

For multi-stage Pipeline V2 workflows, registered artifacts must subsequently be retained in persistent storage before downstream stages can consume them.

Artifact retention is handled by a dedicated worker running independently of the job monitoring service. This separation prevents potentially long-running artifact copying and integrity verification operations from blocking the monitoring loop. See [Pipeline artifact retention](artifact-retention.md) for the retention lifecycle, worker configuration and storage requirements.

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

Artifact retention is configured separately through the dedicated [artifact retention worker](artifact-retention.md).

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

Adapt the installation paths and command-line arguments to your environment. The example uses `/opt/caesar-rest` for the application installation and working directory; persistent scientific data and pipeline artifacts may reside separately under `/storage/caesar-rest`, as described in Deployment [prerequisites](prerequisites.md). The example assumes a local MongoDB instance and access to a separately configured Slurm REST service.

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

### Artifact retention architecture

Artifact registration and retention are intentionally separated from job-status monitoring.

The job monitor is responsible for tracking scientific execution, updating job and pipeline states, and registering output artifacts. Once artifacts have been registered, a dedicated artifact retention worker independently copies and verifies them in persistent storage.

This separation was adopted because artifact retention can involve long-running, blocking filesystem operations, including copying large scientific datasets, computing integrity checksums and promoting directory-based artifacts such as radio-interferometric measurement sets.

Performing these operations synchronously inside the job monitoring loop could delay status updates for other jobs and reduce the responsiveness of the monitoring service.

The architecture therefore separates the two responsibilities:

- **Job monitoring service:** Polls the scheduler, updates MongoDB job and pipeline states, and registers scientific output artifacts.
- **Artifact retention worker:** Processes completed, registered pipeline runs independently, performs artifact copying and integrity verification, and publishes retained outputs for downstream pipeline stages.

The application retains some legacy configuration options and helper functions for automatic retention within the job monitor. However, the current monitoring synchronization path does not invoke synchronous artifact promotion. These options should not be used to configure artifact retention in new deployments.

For production deployments, configure and run the standalone artifact retention worker as described in [Pipeline artifact retention](artifact-retention.md).

The dedicated worker supports persistent artifact storage, configurable retention limits, independent service supervision and explicit retention-state tracking.

Artifact retention failures are handled independently of scientific job execution status. A scientifically completed job can remain completed even when its artifacts are not yet ready for downstream consumption.

## 4. Verify job monitoring

After starting the service, perform the following checks:

1. Confirm that the job monitor systemd unit is active and that the monitoring loop is running without repeated initialization errors.
2. Verify that the monitor can connect to the intended MongoDB database and configured scheduler.
3. Submit a small test job through CAESAR-REST and verify that its state progresses through the expected scheduler states.
4. Confirm that the job's final state is updated in MongoDB after scheduler completion.
5. For scientific pipelines, verify that the corresponding pipeline run reaches its expected terminal state and that successful output artifacts are registered.
6. With the standalone artifact retention worker running, verify that registered artifacts are copied and verified successfully, reach the expected `READY` state, and become available for downstream pipeline stages.

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
