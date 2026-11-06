# CAESAR-REST examples

This section provides practical examples of interacting with CAESAR-REST through its REST API.

The examples cover authentication, dataset management, scientific application discovery, job execution and multi-stage scientific workflows.

Most examples are included directly in the corresponding API guides so that requests, responses and explanations remain together.

## REST API examples

- [Data upload, download and dataset management](../api/data.md) — Upload files, retrieve registered data, manage datasets and configure access.
- [Application discovery and configuration](../api/applications.md) — Discover available scientific applications and inspect their execution options.
- [Job submission and monitoring](../api/jobs.md) — Submit scientific jobs, monitor execution, retrieve results and cancel jobs.
- [Scientific Pipeline V2](../api/scientific-pipelines.md) — Register experiments, submit pipeline runs, manage selections and retained artifacts.

## Integration examples

- [MAASAI integration](../maasai_integration.md) — External agent orchestration of scientific pipelines through the Pipeline V2 API.

The MAASAI and Pipeline V2 examples reflect the currently documented architecture. Their details may evolve as additional scientific workflow capabilities are introduced.

## Usage conventions

Examples use illustrative server URLs, identifiers and scientific inputs. Replace these with values appropriate to the target deployment.

For authentication-enabled installations, protected API requests require a valid OAuth 2.0 bearer access token.

See the [REST API overview](../api/overview.md) and [authentication guide](../deployment/authentication.md) for general request conventions.

The examples complement the [REST API reference](../api/index.md) and do not replace application-specific validation or deployment configuration.
