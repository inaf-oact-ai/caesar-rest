# REST API

CAESAR-REST exposes REST endpoints for dataset management, scientific application discovery, job execution and multi-stage scientific pipeline orchestration.

The API uses the base path `/caesar/api/v1.0`. When authentication is enabled, protected API endpoints require a valid OAuth 2.0 access token supplied through the `Authorization: Bearer` header. See [Keycloak and OpenID Connect authentication](../deployment/authentication.md) for client configuration and authentication workflows.

## Core REST API

- [Overview and authentication conventions](overview.md)
- [Data upload, download and dataset management](data.md)
- [Scientific application discovery and options](applications.md)
- [Job submission, monitoring, output retrieval and cancellation](jobs.md)

These endpoints provide the core operations used by interactive clients and external applications.

## Scientific Pipeline V2

Scientific Pipeline V2 extends CAESAR-REST with explicit pipeline definitions, runs, artifact registration, retention and controlled execution of downstream stages.

- [Scientific Pipeline V2 — concepts and examples](scientific-pipelines.md): Pipeline lifecycle, registration and execution examples.
- [Scientific Pipeline V2 — detailed API reference](../pipeline_v2_api.md): Endpoint contracts, validations, artifact bindings, retention and submission safeguards.
- [MAASAI integration guide](../maasai_integration.md): Agent-driven orchestration of scientific pipelines through the Pipeline V2 API.

The detailed Pipeline V2 API reference provides the more specific contract for client implementations.

## API compatibility and documentation status

CAESAR-REST retains legacy API operations alongside newer dataset-management and Pipeline V2 functionality.

Some examples in the individual API guides originate from earlier CAESAR-REST releases and may not reflect all current request parameters, authorization requirements or response fields.

When developing API clients, verify the documented requests against the installed CAESAR-REST version and use the detailed Pipeline V2 reference for pipeline-specific operations.

Historical material remains available in the [archived original README](../archive/ORIGINAL_README.md).
