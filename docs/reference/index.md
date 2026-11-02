# CLI and container reference

This section provides technical reference information for configuring and running CAESAR-REST services and scientific application containers.

It complements the [installation guide](../installation.md) and [deployment documentation](../deployment/index.md), which describe the recommended setup procedures.

## Reference guides

- [Command-line options](cli-options.md) — Configuration parameters for CAESAR-REST services, including the web application and execution backends.
- [Scientific application containers](app-containers.md) — Container image inventory, Singularity/Apptainer execution and application-specific container information.

## Compatibility and maintenance

CAESAR-REST has evolved from its original Celery-based architecture to support Slurm execution, authenticated datasets and multi-stage scientific pipelines.

Some historical CLI options, container images and image tags remain documented for compatibility but may no longer represent recommended deployment configurations.

Consult the individual reference guides for implementation details and use the [deployment documentation](../deployment/index.md) for current operational recommendations.

Historical configuration and container information is preserved in the [archived original README](../archive/ORIGINAL_README.md).
