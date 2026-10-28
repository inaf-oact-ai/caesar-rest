# CAESAR-REST

CAESAR-REST is a Python/Flask REST service for containerized astronomical processing jobs, data management and authenticated multi-stage scientific pipelines. It supports Slurm and Kubernetes job scheduling, with Celery retained as a legacy backend.

![CAESAR-REST architecture](share/CAESAR-REST_Architecture.png)

## Capabilities

- Application discovery, job submission, job status, cancellation and output retrieval.
- Uploaded and registered datasets, with authenticated access control.
- Scientific Pipeline V2: registered experiments, named immutable input bindings, selection of completed runs and retained artifacts.
- External orchestration integrations, including MAASAI; scientific decisions remain with the orchestrating client.

## Deployment status

| Backend | Status | Guide |
| --- | --- | --- |
| Slurm | Primary, actively developed | [Slurm deployment](docs/deployment/slurm.md) |
| Kubernetes | Secondary; older manifests need review | [Kubernetes deployment](docs/deployment/kubernetes.md) |
| Celery | Legacy/deprecated | [Celery deployment](docs/deployment/celery.md) |

> This first documentation reorganization **preserves** the original README material; its technical instructions are not yet comprehensively updated. Please check the page-level migration notes before executing commands from older examples.

## Documentation

- [Documentation index](docs/index.md)
- [Installation](docs/installation.md)
- [Deployment and services](docs/deployment/index.md)
- [REST API](docs/api/index.md)
- [Examples](docs/examples/index.md)
- [CLI and containers](docs/reference/index.md)
- [Full original README (archived verbatim)](docs/archive/ORIGINAL_README.md)

## Scientific pipelines

- [Pipeline V2 API (migrated README section)](docs/api/scientific-pipelines.md)
- [Detailed Pipeline V2 API guide (already in repository)](docs/pipeline_v2_api.md)
- [MAASAI integration guide (already in repository)](docs/maasai_integration.md)

## License and acknowledgement

Distributed under GPLv3. If CAESAR-REST is used in research, please link to the repository or acknowledge the authors in your publications.

Repository: https://github.com/inaf-oact-ai/caesar-rest
