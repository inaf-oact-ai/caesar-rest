# Kubernetes deployment (secondary backend)

> **Secondary backend — limited validation:** CAESAR-REST retains support for Kubernetes-based scientific job execution, including job submission, cancellation and status monitoring. However, Kubernetes is not the primary actively maintained deployment backend, and the current implementation has not been validated end-to-end against the modern Slurm and Pipeline V2 deployment architecture. **Slurm remains the recommended backend for production deployments.**

This guide describes the Kubernetes integration currently present in CAESAR-REST, its configuration requirements and the limitations of the historical deployment manifests.

The original NEANIAS deployment examples are retained in the repository for reference, but they must not be treated as validated production configurations.

## 1. Architecture

CAESAR-REST supports Kubernetes as an alternative execution backend for scientific application jobs.

In this configuration:

1. The REST application accepts scientific job requests.
2. The Kubernetes backend constructs and submits Kubernetes Job resources.
3. The Kubernetes cluster schedules the corresponding scientific application containers.
4. The standalone job monitoring service queries the execution backend and updates job states in MongoDB.
5. For supported scientific pipelines, output registration and retention are handled by the corresponding pipeline infrastructure.

The REST application and job monitoring service are separate processes. Both must be configured to access the intended Kubernetes cluster and the same CAESAR-REST MongoDB database.

Kubernetes is used to execute scientific jobs; it does not replace MongoDB, the REST application or the services responsible for pipeline state management.

See [Job monitoring](job-monitoring.md) and [Pipeline artifact retention](artifact-retention.md).

## 2. Installation requirements

Install CAESAR-REST with the optional Kubernetes dependency:

```bash
python -m pip install -e '.[kubernetes]'
python -m pip check
```

Add other optional dependencies as required by the REST application deployment, such as authentication or uWSGI support.

The Kubernetes integration additionally requires:

- An accessible Kubernetes cluster.
- Valid credentials for the REST application and monitoring service.
- Sufficient Kubernetes API permissions to create, inspect and delete the relevant Job resources.
- Access to the scientific application container images.
- A supported storage configuration for job inputs and outputs.
- MongoDB accessible to the CAESAR-REST services.

Cluster credentials, service-account permissions, container registry access and storage infrastructure must be configured according to the site's security policies.

The current repository does not provide a fully validated, general-purpose Kubernetes installation procedure.

## 3. Configure the Kubernetes execution backend

Select Kubernetes in the CAESAR-REST application using:

```bash
--job_scheduler=kubernetes
```

The application recognizes the following Kubernetes connection options:

| Option | Description |
| --- | --- |
| `--job_scheduler=kubernetes` | Select Kubernetes as the scientific job execution backend |
| `--kube_incluster` | Use Kubernetes in-cluster client configuration |
| `--kube_config` | Path to an explicit kubeconfig file |
| `--kube_cafile` | Kubernetes API certificate authority file |
| `--kube_keyfile` | Kubernetes API client private key |
| `--kube_certfile` | Kubernetes API client certificate |

When running CAESAR-REST outside Kubernetes, an appropriately configured kubeconfig file can be used.

When the application runs inside a Kubernetes Pod, in-cluster authentication can be selected with `--kube_incluster`, provided that the Pod's service account has the necessary permissions.

For example, the application-side configuration may include:

```bash
--job_scheduler=kubernetes \
--kube_config=/SECURE/PATH/kubeconfig
```

This is a configuration fragment, not a complete CAESAR-REST startup command. Refer to [Web application deployment](web-application.md) for application startup and service configuration.

Certificate files and kubeconfig credentials must be protected from unauthorized access.

### Scientific application images

Kubernetes scientific jobs require container images compatible with the selected CAESAR-REST application.

The job submission implementation resolves the image and execution settings associated with each supported scientific application.

Container availability, image configuration and compatibility must be verified for each application. The presence of a scientific application in the REST registry does not by itself demonstrate that it has been validated on Kubernetes.

## 4. Job storage and rclone integration

The current Kubernetes submission implementation uses a specific remote-storage execution path.

When the application is configured with `--mount_rclone_volume`, the Kubernetes backend constructs jobs through its rclone-based job creation function.

The corresponding application configuration includes options such as:

```bash
--mount_rclone_volume \
--mount_volume_path=/mnt/storage \
--rclone_storage_name=REMOTE_NAME \
--rclone_storage_path=REMOTE_PATH
```

The Kubernetes job configuration also relies on the associated rclone secret and storage settings.

**Implementation limitation:** In the currently inspected job-submission path, Kubernetes jobs cannot be submitted through an alternative local-volume mode when rclone mounting is disabled. The submission function rejects that configuration as an unsupported job volume type.

Therefore, ordinary Kubernetes PersistentVolume support should not be assumed to be sufficient for the current scientific job-submission implementation without corresponding code changes.

For production use, the remote-storage integration must be reviewed for container privileges, credentials, network access, mount behavior and compatibility with the scientific applications.

These requirements are distinct from the shared-filesystem deployment used by the recommended Slurm backend.

## 5. Kubernetes job monitoring

The standalone CAESAR-REST job monitoring service retains Kubernetes-specific status monitoring.

Select Kubernetes using:

```bash
--job_scheduler=kubernetes
```

For example:

```bash
/opt/caesar-rest/venv/bin/run_jobmonitor.py \
	--job_scheduler=kubernetes \
	--job_monitoring_period=30 \
	--dbhost=127.0.0.1 \
	--dbport=27017 \
	--dbname=caesardb \
	--kube_config=/SECURE/PATH/kubeconfig
```

Replace the Python environment, database connection and Kubernetes credentials with deployment-specific settings.

The monitor must use the same Kubernetes cluster and MongoDB database as the REST application.

For an in-cluster deployment, use the corresponding in-cluster authentication options instead of an external kubeconfig, provided the service account has the required permissions.

The availability of Kubernetes monitoring functions does not guarantee that every modern scientific application or Pipeline V2 workflow has been tested with this backend.

See [Job monitoring](job-monitoring.md) for the general monitoring architecture and service supervision.

## 6. Historical Kubernetes deployment manifests

The CAESAR-REST repository retains Kubernetes manifests under:

[`config/kubernetes/`](../../config/kubernetes/)

These manifests originated from earlier deployment configurations and include components associated with the historical NEANIAS architecture.

The repository contains examples of local persistent-storage configurations and remote-storage configurations using rclone.

Some manifests also deploy legacy Celery-related services, including worker and periodic-task components.

For example, historical `caesar-rest-beat-worker.yaml` configurations reference:

- RabbitMQ broker connection parameters.
- Celery queues and result-backend settings.
- Historical `sriggi/caesar-rest-beat-worker:latest` container images.
- PersistentVolumeClaim or rclone-based storage arrangements.

These examples must not be confused with the current Kubernetes scientific Job execution backend.

### Security and compatibility considerations

The historical manifests require review before reuse.

Known concerns include:

- Container image tags referencing historical builds.
- Example credentials embedded directly in environment variables.
- Privileged containers and additional Linux capabilities used for FUSE/rclone mounting.
- Service layouts designed around the legacy Celery deployment.
- Storage paths and persistent-volume configurations specific to the original infrastructure.
- Compatibility with modern Kubernetes security policies and CAESAR-REST dependencies.

In particular, an old manifest using `privileged: true`, `SYS_ADMIN` or direct `/dev/fuse` access should not be deployed unchanged without an explicit security review.

Use Kubernetes Secrets or an approved secret-management solution for credentials rather than copying historical example passwords.

The manifests are preserved as architectural and historical references, not as a certified modern Kubernetes deployment stack.

## 7. Deployment verification

A Kubernetes deployment should be considered validated only after testing the complete application execution lifecycle.

At minimum, verify:

1. The REST application initializes the Kubernetes client successfully.
2. The configured Kubernetes identity has the necessary API permissions.
3. Scientific application images can be pulled and started.
4. Job input and output storage is accessible inside the execution containers.
5. Scientific jobs can be submitted through CAESAR-REST.
6. Jobs complete and their final execution states are recorded in MongoDB.
7. Job cancellation works as expected.
8. The standalone job monitor correctly synchronizes Kubernetes job states.
9. Pipeline artifacts are registered and retained where the selected scientific workflow requires them.

These checks are proposed validation requirements, not a claim that the current Kubernetes backend has passed them.

## 8. Current support status and recommendations

Kubernetes remains available as a secondary CAESAR-REST execution backend, with implementation code for submission, cancellation and monitoring.

However, the repository's historical Kubernetes manifests do not constitute a verified deployment procedure for the current system.

New production deployments should use the maintained [Slurm deployment](slurm.md) unless there is a specific requirement to execute scientific applications through Kubernetes.

Modernizing Kubernetes support would require an independent effort focused on storage integration, security, deployment manifests, application-container compatibility and end-to-end testing.

The existing Kubernetes code and historical manifests should be preserved until such a review determines which components remain useful.

## References

- [Deployment overview](index.md)
- [Installation](../installation.md)
- [Deployment prerequisites](prerequisites.md)
- [Web application deployment](web-application.md)
- [Job monitoring](job-monitoring.md)
- [Pipeline artifact retention](artifact-retention.md)
- [Application CLI options](../reference/cli-options.md)
- [Kubernetes manifests](../../config/kubernetes/)
- [Slurm deployment](slurm.md)
- [Legacy Celery deployment](celery.md)
- [Kubernetes documentation](https://kubernetes.io/docs/)
- [Kubernetes Python client](https://github.com/kubernetes-client/python)
