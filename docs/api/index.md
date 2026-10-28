# REST API

CAESAR-REST exposes REST endpoints under `/caesar/api/v1.0`. When authentication is enabled, protected endpoints require a valid OAuth2 bearer token; see the [authentication and OIDC guide](../deployment/authentication.md).

## Core API

- [Overview and authentication convention](overview.md)
- [Upload, download and datasets](data.md)
- [Application discovery and options](applications.md)
- [Job submission, status, output and cancellation](jobs.md)

## Scientific pipelines

- [Scientific Pipeline V2 — introduction and examples](scientific-pipelines.md): concepts, lifecycle, registration and selection examples migrated from the original README.
- [Scientific Pipeline V2 — detailed API reference](../pipeline_v2_api.md): route contract, validations, named artifacts, retention and submission safeguards.
- [MAASAI integration guide](../maasai_integration.md): external agent orchestration using the Pipeline V2 contract.

> Some JSON examples in the migrated pages are historical examples from the original README, not claims about a live deployment. Consult the detailed API reference and the application's live description for current behavior.
