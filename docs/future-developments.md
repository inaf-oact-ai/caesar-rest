# Future developments and integrations

CAESAR-REST is under active development. This page distinguishes **capabilities already implemented on `devel`** from **possible directions for future work**. The latter are not release commitments or guarantees of availability.

## Current foundation

CAESAR-REST already provides independent containerized application jobs, authenticated dataset access, and Scientific Pipeline V2 functionality on Slurm-based deployments. The pipeline API supports experiment registration, immutable named artifact bindings, preferred-run selection, and retained artifacts for downstream execution.

For implementation details, see the [Scientific Pipeline V2 overview](api/scientific-pipelines.md) and [detailed REST API reference](pipeline_v2_api.md).

### Agent-driven scientific workflows: MAASAI

The existing [MAASAI integration guide](maasai_integration.md) documents the tested R1–R3B client/server contract. MAASAI can act as an **external orchestration client**: proposing experiments, submitting registered runs, monitoring their execution, comparing scientific outcomes, and selecting preferred runs. CAESAR-REST manages validation, execution, recorded dependencies, and artifact retention.

**Important boundary:** CAESAR-REST does not independently optimize scientific parameters, select the best experiment, or automatically execute downstream stages. These decisions remain with an external client such as MAASAI.

Potential future improvements to this integration include richer experiment and provenance views, more convenient client tooling, and further operational testing of complete multi-stage workflows. These are development directions, not features asserted to be present.

## Areas for future work

### Kubernetes backend evolution

Slurm is the current primary development and validation target. Kubernetes support and deployment manifests exist, but need review and further validation against the current application, authentication, dataset, and pipeline infrastructure.

See the [Kubernetes deployment guide](deployment/kubernetes.md) for the existing material and its limitations.

### Additional scientific applications and pipeline stages

The pipeline layer is designed to be application-independent, with application-specific scientific policies and execution configuration supplied by the server. Additional application integrations and stages may be introduced incrementally as their containers, configuration, inputs, and artifact contracts are implemented and validated.

The OXKAT examples in the [Pipeline V2 API reference](pipeline_v2_api.md) demonstrate this architecture; they should not be interpreted as a guarantee that every proposed stage or option is operational in every deployment.

### Operations, documentation, and reproducibility

Further work may improve installation and deployment reproducibility, automated checks, service monitoring, artifact retention operations, and documentation coverage. Existing deployment examples will be reviewed page by page against the current `devel` code and tested installations.

## How to follow development

- [Repository and `devel` branch](https://github.com/inaf-oact-ai/caesar-rest/tree/devel)
- [Documentation index](index.md)
- [REST API documentation](api/index.md)
- [MAASAI integration guide](maasai_integration.md)

This page intentionally avoids fixed dates and release promises. As a feature is implemented and validated, its authoritative usage and API details should move to the relevant documentation page, with this page retaining only future-looking context.
