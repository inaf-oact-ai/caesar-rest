# Deployment

The original deployment material has been separated into service-oriented pages without changing its technical examples.

| Mode | Status | Guide |
| --- | --- | --- |
| Slurm | Primary, active development | [Slurm](slurm.md) |
| Kubernetes | Secondary; dedicated guide currently only indexes existing manifests | [Kubernetes](kubernetes.md) |
| Celery | Legacy, deprecated | [Celery](celery.md) |

## Shared services

- [Preparatory setup, MongoDB and Filebeat](prerequisites.md)
- [Web application and NGINX/uWSGI](web-application.md)
- [HTTPS reverse proxy configuration](https-reverse-proxy.md)
- [Keycloak / OIDC authentication and TLS](authentication.md)
- [Job monitoring](job-monitoring.md)
- [Pipeline artifact retention](artifact-retention.md)
- [Accounting](accounting.md)
- [CLI options](../reference/cli-options.md)

> Deployment snippets are historical source material and must be reviewed before production use.
