# CAESAR-REST

CAESAR-REST is an authenticated REST service for executing containerized scientific applications on compute infrastructure. Originally developed to provide a web interface for [CAESAR source finder](https://github.com/SKA-INAF/caesar), it now supports multiple astronomical and data-analysis applications, dataset management, independent jobs, and multi-stage scientific workflows.

![CAESAR-REST architecture](share/CAESAR-REST_Architecture.png)

## Capabilities

- Application discovery, job submission, job status, cancellation and output retrieval.
- Uploaded and registered datasets, with authenticated access control.
- Scientific Pipeline V2: registered experiments, named immutable input bindings, selection of completed runs and retained artifacts.
- External orchestration integrations, including MAASAI Agent System; scientific decisions remain with the orchestrating client.

## Development Status

The `devel` branch is under active development, with periodic merge into `master` branch and software releases. 
The original code was developed in Python 2.7, then switched to Python 3.6. Current development is being tested for Python 3.8/3.10.

CAESAR-REST supports multiple job submission backends

| Backend | Status | Guide |
| --- | --- | --- |
| Slurm | Primary, actively developed | [Slurm deployment](docs/deployment/slurm.md) |
| Kubernetes | Secondary; older manifests need review | [Kubernetes deployment](docs/deployment/kubernetes.md) |
| Celery | Legacy/deprecated | [Celery deployment](docs/deployment/celery.md) |

## Documentation

- [Documentation index](docs/index.md)
- [Full original README (archived verbatim)](docs/archive/ORIGINAL_README.md)
- [Installation](docs/installation.md)
- [Deployment and services](docs/deployment/index.md)
- [REST API](docs/api/index.md)
- [Examples](docs/examples/index.md)
- [CLI and containers](docs/reference/index.md)
- [Pipeline V2 API (migrated README section)](docs/api/scientific-pipelines.md)
- [Detailed Pipeline V2 API guide (already in repository)](docs/pipeline_v2_api.md)
- [MAASAI integration guide (already in repository)](docs/maasai_integration.md)

## License and acknowledgement

Distributed under GPLv3. If CAESAR-REST is used in research, please link to the repository (`https://github.com/inaf-oact-ai/caesar-rest`) and acknowledge/cite the following papers in your publications:

- S. Riggi, *Astronomical source finding services for the CIRASA visual analytic platform*, Astronomy & Computing, 37, 100506 (2021), [doi](https://doi.org/10.1016/j.ascom.2021.100506) 
