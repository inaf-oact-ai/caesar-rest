# Deployment

This section describes how to deploy CAESAR-REST and its supporting services. Slurm is the recommended execution backend, with Kubernetes available as a secondary backend. The documentation covers application installation, persistent storage, HTTPS and authentication, job monitoring, artifact retention, and optional supporting services. Configuration examples are illustrative and must be adapted to the target infrastructure.

| Backend | Status | Documentation |
| --- | --- | --- |
| Slurm | Recommended and actively maintained | [Slurm deployment](slurm.md) |
| Kubernetes | Supported as a secondary backend; existing manifests require review | [Kubernetes deployment](kubernetes.md) |
| Celery | Legacy, no longer actively maintained | [Celery legacy deployment](celery.md) |

## Shared services

- [Preparatory setup, MongoDB and Filebeat](prerequisites.md)
- [Web application and NGINX/uWSGI](web-application.md)
- [Keycloak / OIDC authentication and TLS](authentication.md)
- [Job monitoring](job-monitoring.md)
- [Pipeline artifact retention](artifact-retention.md)
- [Accounting](accounting.md)
- [CLI options](../reference/cli-options.md)

> **Deployment note**: The examples in these guides are intended as reference configurations, not universally applicable production settings. Adapt service accounts, filesystem paths, scheduler endpoints, TLS certificates and security controls to your infrastructure. Legacy deployment materials are identified explicitly in their respective guides.
