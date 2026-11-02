# CAESAR-REST

CAESAR-REST is an authenticated REST service for executing containerized scientific applications on distributed computing infrastructure.

Originally developed as a web interface for the [CAESAR source finder](https://github.com/SKA-INAF/caesar), it has evolved into a general-purpose service supporting astronomical data analysis, scientific application execution, dataset management and multi-stage scientific workflows.

CAESAR-REST separates scientific job submission and orchestration from the application-specific execution environments, enabling different scientific tools to be integrated through a common REST interface.

<p align="left">
  <img src="share/CAESAR-REST_Architecture.png" alt="CAESAR-REST architecture" width="600">
</p>

## Main capabilities

- **Scientific application execution:** Discover available applications, configure scientific jobs, submit them, monitor execution, cancel jobs and retrieve results.
- **Containerized applications:** Execute scientific software in Singularity/Apptainer containers through Slurm, with additional backend integrations.
- **Authentication and authorization:** Integrate with Keycloak/OpenID Connect to authenticate users and protect scientific resources.
- **Dataset management:** Upload data, register managed datasets and enforce owner-scoped access controls.
- **Job monitoring:** Track scientific execution through persistent job records and a dedicated monitoring service.
- **Scientific Pipeline V2:** Register experiments, manage immutable upstream artifact bindings, compare alternative runs and select preferred scientific results.
- **Artifact retention:** Preserve registered scientific outputs in managed storage for subsequent processing stages.
- **External orchestration:** Support integration with scientific workflow managers and agent systems, including MAASAI.

Scientific decisions and experiment selection remain the responsibility of the user or external orchestration system.

## Execution backends

CAESAR-REST supports multiple execution backends.

| Backend | Status | Documentation |
| --- | --- | --- |
| **Slurm** | Primary, actively maintained backend | [Slurm deployment](docs/deployment/slurm.md) |
| **Kubernetes** | Secondary backend; deployment requires additional validation | [Kubernetes deployment](docs/deployment/kubernetes.md) |
| **Celery** | Legacy backend, retained for compatibility | [Celery deployment](docs/deployment/celery.md) |

Slurm is the recommended backend for current deployments.

## Development status

CAESAR-REST is under active development.

The `devel` branch contains ongoing implementation work, while stable functionality may be merged into the main release branch.

The codebase originated in Python 2 and has since been migrated to Python 3. The supported Python interpreter matrix has not yet been formally established in the package metadata; use the installation and deployment documentation for the currently tested environment.

Scientific Pipeline V2 is being extended to support additional scientific workflow requirements, including multi-target observation processing.

## Documentation

Detailed documentation is organized into the following sections:

| Section | Contents |
| --- | --- |
| [Installation](docs/installation.md) | Software installation and environment preparation |
| [Deployment](docs/deployment/index.md) | Slurm, HTTPS, Keycloak authentication, job monitoring and supporting services |
| [REST API](docs/api/index.md) | Data and datasets, applications, jobs and scientific pipelines |
| [Examples](docs/examples/index.md) | Practical REST requests and workflow examples |
| [CLI and container reference](docs/reference/index.md) | Command-line configuration and scientific container images |
| [Scientific Pipeline V2](docs/api/scientific-pipelines.md) | Pipeline architecture, execution lifecycle, API endpoints and artifact management |
| [MAASAI integration](docs/maasai_integration.md) | External agent-oriented scientific orchestration |
| [Future developments](docs/future-developments.md) | Planned capabilities and future integrations |

For the complete navigation structure, see the [documentation index](docs/index.md).

## License

CAESAR-REST is distributed under the terms of the **GNU General Public License version 3 (GPLv3)**.

See the [LICENSE](LICENSE) file.

## Citation and acknowledgement

If you use CAESAR-REST in scientific research, please acknowledge the project and cite the following publication:

S. Riggi, *Astronomical source finding services for the CIRASA visual analytic platform*, Astronomy & Computing, **37**, 100506 (2021).

DOI: [10.1016/j.ascom.2021.100506](https://doi.org/10.1016/j.ascom.2021.100506)

Project repository: [inaf-oact-ai/caesar-rest](https://github.com/inaf-oact-ai/caesar-rest).
