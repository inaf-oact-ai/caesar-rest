# CAESAR-REST command-line reference

This guide documents the command-line configuration options for the CAESAR-REST web application and its principal supporting services.

The reference is based on the argument parsers in the `devel` branch:

- `apps/run_app.py`
- `apps/run_jobmonitor.py`
- `apps/run_artifact_retention.py`

The parser definitions are the source of truth for supported flags and default values. Options may evolve between releases; consult `--help` for the installed version.

For recommended deployment procedures, see the [deployment guide](../deployment/index.md).

## 1. Command-line conventions

CAESAR-REST uses Python `argparse`.

Options accepting values are generally supplied using either:

```bash
--option=value
```

or:

```bash
--option value
```

Boolean flags are enabled by specifying the flag without a value.

For example:

```bash
python apps/run_app.py \
	--job_scheduler=slurm \
	--aai \
	--dbhost=localhost \
	--dbport=27017
```

The web application and job-monitoring service accept many of the same settings, but each has its own parser and defaults.

The artifact-retention service has a separate, smaller CLI.

Do not assume that every option supported by `run_app.py` is also supported by the standalone services.

## 2. Web application

**Entrypoint:** `apps/run_app.py`

The web application exposes the REST API, manages authentication, validates scientific jobs and submits them through the configured execution backend.

### 2.1 General options

| Option | Description | Default |
| --- | --- | --- |
| `--datadir` | Root directory for uploaded data | `/opt/caesar-rest/data` |
| `--jobdir` | Root directory for job data | `/opt/caesar-rest/jobs` |
| `--modeldir` | Root directory for model files | `/opt/caesar-rest/models` |
| `--job_scheduler` | Execution backend: `slurm`, `kubernetes` or legacy `celery` | `slurm` |
| `--job_monitoring_period` | Configured job-monitoring interval | `5` |
| `--debug` | Enable Flask debug mode | Disabled |
| `--ssl` | Enable the application's built-in HTTPS mode | Disabled |

**Slurm is the default backend** in the current application parser.

The default scheduler setting does not eliminate the need for correct Slurm service credentials, storage mounts and execution configuration.

For production HTTPS deployments, use the recommended reverse-proxy configuration instead of relying on Flask's development server.

See [Web application deployment](../deployment/web-application.md).

### 2.2 Authentication and OpenID Connect

| Option | Description | Default |
| --- | --- | --- |
| `--aai` | Enable identity-provider authentication | Disabled |
| `--secretfile` | OpenID Connect client credentials JSON file | `config/client_secrets.json` |
| `--openid_realm` | Identity-provider realm | `neanias-development` |

The defaults reflect the parser, not a recommended production Keycloak configuration.

Authentication-enabled deployments must provide the correct identity-provider settings, client credentials, public URLs and TLS configuration.

See [Keycloak and OIDC authentication](../deployment/authentication.md).

### 2.3 MongoDB options

| Option | Description | Default |
| --- | --- | --- |
| `--dbhost` | MongoDB hostname | `localhost` |
| `--dbport` | MongoDB port | `27017` |
| `--dbname` | MongoDB database name | `caesardb` |
| `--db` | Enable database use | Parser-dependent boolean configuration |
| `--no-db` | Disable database use | Not selected |

The current scientific job and pipeline infrastructure relies on persistent MongoDB records for jobs, pipelines, submissions, datasets and artifacts.

Disabling database integration is not a recommended configuration for these workflows.

### 2.4 Logging

| Option | Description | Default |
| --- | --- | --- |
| `--loglevel` | Logging level | `INFO` |
| `--logtofile` | Enable file logging | Disabled |
| `--logdir` | Log directory | `/opt/caesar-rest/logs` |
| `--logfile` | Log filename | `app_logs.json` |
| `--logfile_maxsize` | Maximum log-file size in MB | `5.0` |

Production deployments should configure appropriate log retention, permissions and monitoring.

## 3. Slurm backend options

These options configure the Slurm execution integration used by the web application.

| Option | Description | Parser default |
| --- | --- | --- |
| `--slurm_keyfile` | Slurm REST service private-key file | Empty |
| `--slurm_user` | Slurm execution identity | `cirasa` |
| `--slurm_host` | Slurm REST service hostname | `localhost` |
| `--slurm_port` | Slurm REST service port | `6820` |
| `--slurm_batch_workdir` | Directory for Slurm batch logs | `/opt/slurm/batchlogs/caesar-rest` |
| `--slurm_queue` | Slurm partition or queue | `normal` |
| `--slurm_jobdir` | Job directory as visible from the Slurm environment | `/mnt/storage/jobs` |
| `--slurm_datadir` | Data directory as visible from the Slurm environment | `/mnt/storage/data` |
| `--slurm_modeldir` | Model directory as visible from the Slurm environment | `/mnt/storage/models` |
| `--slurm_max_cores_per_job` | Configured maximum CPU cores per job | `4` |

The default `slurm_user` value is historical and must be replaced with the correct account for the target cluster.

CAESAR-REST and the Slurm environment must agree on the location and visibility of job data, input datasets, models and pipeline artifacts.

See [Slurm deployment](../deployment/slurm.md).

## 4. Scientific Pipeline V2 configuration

The web application includes options controlling staged execution, supported pipeline applications and artifact retention.

| Option | Description | Default |
| --- | --- | --- |
| `--pipeline_staged_execution_enabled` | Enable staged pipeline execution | Disabled |
| `--pipeline_staged_applications` | Comma-separated applications permitted to use staged execution | `oxkat` |
| `--pipeline_python_executable` | Python executable configured for the staged pipeline infrastructure | `/usr/bin/python3` |
| `--pipeline_v2_applications` | JSON configuration of Pipeline V2 application support | `{}` |

Staged pipeline execution is enabled only when explicitly configured.

The configured application must support the corresponding staged-execution contract. Merely adding an application name to the allowed list does not establish compatibility.

Pipeline V2 scientific options, stage policies and artifact requirements are also validated by the application-specific configurator.

The current implementation includes OxKAT-specific scientific configuration support.

### 4.1 Artifact-retention options

| Option | Description | Default |
| --- | --- | --- |
| `--pipeline_artifact_retention_root` | Managed artifact-retention root | Empty |
| `--pipeline_artifact_retention_root_cluster` | Artifact-retention root as visible in the cluster environment | Empty |
| `--pipeline_artifact_retention_max_file_bytes` | Maximum retained file size, bytes | `1073741824` |
| `--pipeline_artifact_retention_max_directory_bytes` | Maximum retained directory size, bytes | `1099511627776` |
| `--pipeline_artifact_retention_max_directory_entries` | Maximum directory entry count | `100000` |
| `--pipeline_artifact_retention_max_directory_depth` | Maximum directory traversal depth | `16` |

The size limits correspond to 1 GiB per file and 1 TiB per directory by default.

The artifact-retention root must be configured appropriately for pipelines that retain outputs and execute downstream stages.

Retention copying is performed by the dedicated retention service, rather than synchronously by the REST endpoint.

See [Pipeline artifact retention](../deployment/artifact-retention.md).

## 5. Managed dataset registry

The web application supports a managed dataset registry with authorization rules separate from the historical static dataset configuration.

| Option | Description | Default |
| --- | --- | --- |
| `--dataset_registry_enabled` | Enable managed dataset registry functionality | Disabled |
| `--dataset_allowed_roots` | Configured filesystem roots permitted for managed datasets | Empty |
| `--dataset_admin_identities` | Configured identities authorized for dataset administration | Empty |

Managed dataset paths are validated against the allowed roots, and dataset operations are subject to the configured authentication and authorization rules.

For multi-user scientific pipeline execution, configure the registry, allowed roots and administrative identities consistently.

See [Data and datasets API](../api/data.md).

## 6. Scientific application containers

The web application accepts container-path options for individual scientific applications.

The following options are present in the current parser:

| Option | Scientific application |
| --- | --- |
| `--caesar_container` | CAESAR source finding |
| `--aegean_container` | Aegean |
| `--cutex_container` | CuTEx |
| `--mrcnn_container` | Mask R-CNN |
| `--cnn_classifier_container` | CNN classifier |
| `--vit_classifier_container` | Vision Transformer classifier |
| `--umap_container` | UMAP |
| `--outlier_finder_container` | Outlier finder |
| `--hdbscan_container` | HDBSCAN |
| `--simsearch_container` | Similarity search |
| `--caesar_yolo_container` | CAESAR YOLO |
| `--sfforecaster_container` | Solar flare forecasting |
| `--fextractor_tf_container` | Fextractor TensorFlow backend |
| `--fextractor_torch_container` | Fextractor PyTorch backend |
| `--fextractor_chronos_container` | Fextractor Chronos backend |
| `--fextractor_moirai_container` | Fextractor Moirai backend |
| `--fextractor_fats_container` | Fextractor FATS backend |
| `--fextractor_licu_container` | Fextractor LICU backend |
| `--fextractor_falcon_container` | Fextractor Falcon backend |
| `--oxkat_container` | OxKAT |

The current parser also exposes the legacy `--mrcnn_weights` option for an application-specific weights path.

Container-path defaults are defined directly in `apps/run_app.py` and typically refer to `.sif` images under `/opt/containers/`.

The existence of a container option does not guarantee that the image is installed, accessible or compatible with the current scientific application version.

See [Scientific application containers](app-containers.md) for container inventory and compatibility notes.

## 7. Kubernetes backend

The web application supports the following Kubernetes connection options.

| Option | Description | Default |
| --- | --- | --- |
| `--kube_incluster` | Use Kubernetes in-cluster configuration | Disabled |
| `--kube_config` | Kubernetes configuration file path | Empty; standard lookup |
| `--kube_cafile` | Kubernetes certificate-authority file | Empty |
| `--kube_keyfile` | Kubernetes private-key file | Empty |
| `--kube_certfile` | Kubernetes client certificate file | Empty |

Kubernetes is a secondary execution backend.

Its deployment and storage requirements differ from those of Slurm, and some historical Kubernetes manifests still refer to legacy Celery infrastructure.

See [Kubernetes deployment](../deployment/kubernetes.md).

## 8. Legacy Celery configuration

The web application retains options for its historical Celery execution backend.

| Option | Description | Default |
| --- | --- | --- |
| `--result_backend_host` | Result backend hostname | `localhost` |
| `--result_backend_port` | Result backend port | `6379` |
| `--result_backend_proto` | Result backend protocol | `redis` |
| `--result_backend_user` | Result backend username | Empty |
| `--result_backend_pass` | Result backend password | Empty |
| `--result_backend_dbname` | Result backend database name | `0` |
| `--broker_host` | Message broker hostname | `localhost` |
| `--broker_port` | Message broker port | `5672` |
| `--broker_proto` | Message broker protocol | `amqp` |
| `--broker_user` | Message broker username | `guest` |
| `--broker_pass` | Message broker password | `guest` |

Celery is retained for compatibility and is not the recommended execution backend for new deployments.

The `guest` credentials are historical defaults suitable only for isolated development configurations. Production systems must use appropriately secured service credentials.

See [Legacy Celery deployment](../deployment/celery.md).

## 9. Volume mounting and rclone

| Option | Description | Default |
| --- | --- | --- |
| `--mount_rclone_volume` | Enable rclone-based remote volume mounting for supported container jobs | Disabled |
| `--mount_volume_path` | Container-side mount path | `/mnt/storage` |
| `--rclone_storage_name` | rclone remote name | `neanias-nextcloud` |
| `--rclone_storage_path` | Remote path | `.` |

These are retained from the existing remote-storage integration.

Their applicability depends on the selected execution backend and application container.

They should not be confused with managed dataset registration or Pipeline V2 artifact retention.

## 10. Historical statically configured datasets

The web application retains CLI options for historical dataset configuration:

```text id="peic8e"
--dataset_smgps
--dataset_smgps_feats_simclr
--dataset_smgps_feats_siglip
--dataset_smgps_feats_dinov2
--dataset_emu_pilot
--dataset_emu
--dataset_emu_scorpio_pilot
--dataset_emu_gp_pilot
```

These options specify paths associated with the corresponding statically configured scientific datasets.

They are maintained separately from the newer managed dataset registry.

When the managed registry is enabled, registered dataset IDs and authorization checks should be used for modern multi-user scientific workflows.

## 11. Standalone job-monitoring service

**Entrypoint:** `apps/run_jobmonitor.py`

This service monitors jobs submitted through the configured execution backend and updates persisted job states.

The parser supports the following primary options:

| Option | Description | Default |
| --- | --- | --- |
| `--job_scheduler` | Monitoring backend: `slurm` or `kubernetes` | `slurm` |
| `--job_monitoring_period` | Polling interval in seconds | `30` |
| `--dbhost` | MongoDB hostname | `localhost` |
| `--dbport` | MongoDB port | `27017` |
| `--dbname` | MongoDB database name | `caesardb` |

It also supports the same principal Kubernetes connection and Slurm REST connection flags described earlier, along with logging configuration.

An illustrative invocation is:

```bash
python apps/run_jobmonitor.py \
	--job_scheduler=slurm \
	--dbhost=localhost \
	--dbport=27017 \
	--dbname=caesardb \
	--job_monitoring_period=30
```

The standalone monitor does not use the web application's `--job_monitoring_period` default. Its own parser defaults to 30 seconds.

See [Job monitoring deployment](../deployment/job-monitoring.md).

## 12. Artifact-retention service

**Entrypoint:** `apps/run_artifact_retention.py`

This process performs asynchronous retention of registered pipeline outputs into managed storage.

Its command-line options are:

| Option | Description | Default |
| --- | --- | --- |
| `--dbhost` | MongoDB hostname | `localhost` |
| `--dbport` | MongoDB port | `27017` |
| `--dbname` | MongoDB database | `caesardb` |
| `--retention-root` | Managed output retention directory | Required |
| `--poll-seconds` | Polling interval in seconds | `30` |
| `--max-file-bytes` | Maximum permitted retained file size | `1073741824` |
| `--max-directory-bytes` | Maximum permitted retained directory size | `1099511627776` |
| `--max-directory-entries` | Maximum directory entry count | `100000` |
| `--max-directory-depth` | Maximum directory traversal depth | `16` |

An illustrative invocation is:

```bash
python apps/run_artifact_retention.py \
	--dbhost=localhost \
	--dbname=caesardb \
	--retention-root=/storage/caesar-rest/pipeline-artifacts \
	--poll-seconds=30
```

The retention root must match the storage layout and access requirements of the CAESAR-REST pipeline deployment.

For downstream pipeline stages, retained scientific outputs must remain accessible to the execution infrastructure according to the configured path mappings.

See [Pipeline artifact retention deployment](../deployment/artifact-retention.md).

## 13. Operational considerations

The CLI defaults describe parser behavior. They do not necessarily represent a complete or secure production configuration.

For production deployments:

- Prefer Slurm where it is the supported and validated execution backend.
- Enable and correctly configure authentication for externally accessible services.
- Configure persistent MongoDB storage and appropriate service permissions.
- Align application, cluster and retention storage paths.
- Configure managed dataset access rules for multi-user scientific workflows.
- Run the standalone monitoring and retention services when required.
- Validate that scientific container images exist and are accessible from execution nodes.
- Protect credential files, certificates and private keys.

This reference documents available configuration flags, not an end-to-end deployment procedure.

## References

- [Installation](../installation.md)
- [Deployment overview](../deployment/index.md)
- [Web application deployment](../deployment/web-application.md)
- [Slurm deployment](../deployment/slurm.md)
- [Kubernetes deployment](../deployment/kubernetes.md)
- [Job monitoring](../deployment/job-monitoring.md)
- [Artifact retention](../deployment/artifact-retention.md)
- [Dataset management API](../api/data.md)
- [Scientific application containers](app-containers.md)
- [Original README archive](../archive/ORIGINAL_README.md)
