# CAESAR-REST pipeline V2 REST API

This document describes the agent-oriented pipeline API implemented on the CAESAR-REST `devel` branch at the end of R3B (October 2026). It complements, rather than replaces, the existing `/job` APIs and legacy node-oriented pipeline endpoints.

## API conventions

- Base prefix: `/caesar/api/v1.0`; all paths below are relative to that prefix.
- Pipeline endpoints require an authenticated identity. API clients supply their Keycloak/OIDC bearer token using `Authorization: Bearer <access-token>`; deployment-specific authentication configuration is documented in the project README.
- Pipeline and run records, selections, and artifacts are owner scoped. A run from a different owner or pipeline cannot be bound as an input.
- JSON examples show application `oxkat`, but pipeline metadata, logical nodes, run selection, and artifact binding are application-independent. Allowed applications, stages, and scientific parameters are controlled by server-side configuration.
- Identifiers shown as `PIPELINE_ID`, `RUN_ID`, etc. are placeholders.
- A run reservation is distinct from the scheduler job created when the run is submitted.

## Concepts

| Concept | Meaning |
| --- | --- |
| Pipeline | Owner-scoped collection of experiments and execution history for a scientific workflow. |
| Stage | Scientific operation validated by the configured application (e.g. `GET_INFO`, `1GC`, `FLAG`, `2GC` for OXKAT). |
| Node | Logical grouping of alternative runs for a stage. Omission of `node_id` uses the generic default `stage_<stage-lowercase>` (e.g. `stage_2gc`). Custom node IDs permit separate experimental groups. |
| Run | A registered experiment with immutable scientific parameters and input bindings. |
| Selection | Mutable pointer to a preferred **completed** run of a node. |
| Artifact binding | Immutable downstream input reference to a specific upstream run and artifact, with retained-data integrity metadata. |
| Retention | Copy and verification of registered output files/directories into managed long-lived artifact storage. |

A preferred run may change, but existing downstream input bindings do not change.

## Route reference

### Pipelines and runs

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/pipelines` | Create a pipeline. |
| `GET` | `/pipelines` | List owner-visible pipelines. |
| `GET` | `/pipelines/{pipeline_id}` | Retrieve pipeline metadata, including selection state. |
| `GET` | `/pipelines/{pipeline_id}/runs` | List runs without specifying a node. |
| `POST` | `/pipelines/{pipeline_id}/runs` | Register a simplified V2 run. |
| `GET` | `/pipelines/{pipeline_id}/runs/{run_id}` | Retrieve run status, bindings, readiness, selection and submission details. |
| `POST` | `/pipelines/{pipeline_id}/runs/{run_id}/submit` | Submit a reserved V2 run using an empty JSON object. |
| `GET` | `/pipelines/{pipeline_id}/tree` | Return nodes and runs with summary, selection, readiness and submission data. |
| `POST` | `/pipelines/{pipeline_id}/sync` | Reconcile associated pipeline runs from existing persisted job records. |

### Legacy-compatible node routes, selections and artifacts

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs` | List or register runs using the node-oriented/legacy contract. |
| `POST` | `/pipelines/{pipeline_id}/nodes/{node_id}/selection` | Unconditionally select a completed run (last writer wins). |
| `PUT` | `/pipelines/{pipeline_id}/nodes/{node_id}/selection` | Conditionally select a completed run using optimistic concurrency. |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/artifacts` | List registered artifacts. |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/artifacts/{index}` | Download a retained, registered file artifact. |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/selected/artifacts/{artifact_name}` | Resolve named artifact of the currently selected run. |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/selected/directories/{artifact_name}` | Verify/resolve a selected retained directory by identity. |
| `POST` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/retain` | Queue output retention; copying is handled outside the request. |

Directory artifacts are not ordinary single-file downloads. Use the directory resolver and managed downstream binding instead of assuming a download or host filesystem path.

## Create a pipeline

```http
POST /caesar/api/v1.0/pipelines
Content-Type: application/json
Authorization: Bearer ACCESS_TOKEN
```

```json
{
  "app": "oxkat",
  "name": "MeerKAT calibration experiments",
  "description": "Compare alternative calibration and flagging configurations"
}
```

The response includes a server-generated `pipeline_id`. Application identity is a first-class pipeline property; the compatibility fallback for older metadata is handled by the server.

## Register an experiment

```http
POST /caesar/api/v1.0/pipelines/PIPELINE_ID/runs
Content-Type: application/json
```

The simplified payload accepts `stage`, optional `node_id`, optional `parameters`, optional `dataset_id`, and either `inputs` or legacy `input_artifacts` (not both).

### Initial dataset-bound stage

```json
{
  "stage": "GET_INFO",
  "dataset_id": "oxkat-test-dataset-v3"
}
```

The server validates the stage and derives the corresponding execution configuration. Dataset use is subject to the server's dataset-access and stage policies.

### Explicit upstream run references (R2A)

```json
{
  "stage": "2GC",
  "inputs": {
    "target_ms": {
      "run_id": "FLAG_RUN_ID",
      "artifact": "flagged_target_measurement_sets"
    },
    "flag_images": {
      "run_id": "FLAG_RUN_ID",
      "artifact": "flag_images"
    },
    "project_info": {
      "run_id": "FLAG_RUN_ID",
      "artifact": "project_info"
    }
  }
}
```

### Preferred upstream node references (R2B)

```json
{
  "stage": "2GC",
  "node_id": "imaging_candidate_a",
  "inputs": {
    "target_ms": {
      "node_id": "flag",
      "selected": true,
      "artifact": "flagged_target_measurement_sets"
    },
    "flag_images": {
      "node_id": "flag",
      "selected": true,
      "artifact": "flag_images"
    },
    "project_info": {
      "node_id": "flag",
      "selected": true,
      "artifact": "project_info"
    }
  }
}
```

`selected` must be JSON boolean `true`, not a string or numeric value. A named input is either `{run_id, artifact}` or `{node_id, selected, artifact}` with exactly those fields. Mixing both forms **across different inputs** is allowed. The server reads one pipeline-selection snapshot per registration, resolves selected pointers into explicit upstream IDs, and freezes every input before creating the run. Upstream runs must be completed, their artifacts registered and their required retained data available for binding. A missing selection, unavailable artifact or invalid reference is rejected.

Successful registration returns HTTP `201` and a `PLANNED` run with `run_id`, `node_id`, `run_name`, `sequence`, `input_runs` and concrete `input_artifacts` entries (including source run and artifact index). Registration does not submit to Slurm.

## Submit a registered V2 run

```http
POST /caesar/api/v1.0/pipelines/PIPELINE_ID/runs/RUN_ID/submit
Content-Type: application/json

{}
```

The endpoint reconstructs job options from the reserved run. Clients must **not** resupply scientific parameters or storage paths. The server enforces stage policy, dataset binding, frozen input integrity and scheduler settings. Normal success returns HTTP `200` with job submission information.

A run is submitted only once. The underlying implementation atomically claims `PLANNED` runs, writes a durable one-shot submission intent before contacting Slurm, and does not automatically retry uncertain outcomes. An HTTP timeout does not prove the scheduler rejected the job.

## Inspect run state and readiness

```http
GET /caesar/api/v1.0/pipelines/PIPELINE_ID/runs/RUN_ID
```

Selected fields from a planned downstream run:

```json
{
  "status": "PLANNED",
  "artifacts_status": "NOT_REGISTERED",
  "readiness": {
    "can_select": false,
    "can_consume": false
  },
  "selected": false,
  "submission": {
    "state": "NOT_STARTED",
    "job_id": null,
    "retry_allowed": true,
    "requires_reconciliation": false
  }
}
```

Important distinctions:

- `status` is the scientific/pipeline run lifecycle: `PLANNED`, `SUBMITTING`, `SUBMITTED`, `SUBMISSION_FAILED`, `SUBMISSION_UNCERTAIN`, `RUNNING`, `COMPLETED`, `FAILED` or `CANCELLED`.
- `artifacts_status` describes **outputs** of this run, not the already frozen upstream `input_artifacts`. It may be `NOT_REGISTERED`, `REGISTERED`, `PENDING`, `COPYING`, `FAILED` or `READY` depending on persisted metadata and retention progress.
- `readiness.can_select` is `true` only for scientifically `COMPLETED` runs; scientific selection does not require retention.
- `readiness.can_consume` reports whether the full registered artifact set has retained metadata consistent with readiness. It does **not** perform a full filesystem rehash or guarantee suitability for every downstream stage; the binding layer performs authoritative integrity and eligibility checks.
- `selected` reports whether this run currently matches the node's preferred selection.
- `submission.state` uses `NOT_STARTED`, `IN_PROGRESS`, `SUBMITTED`, `ACCEPTED`, `FAILED`, `UNCERTAIN`, or `UNKNOWN`. `ACCEPTED` means scheduler submission occurred, **not** successful scientific computation.
- `submission.retry_allowed` is true only for a `PLANNED` run. It signals lifecycle eligibility for a first submission, not permission for blind HTTP retries after an unknown result.
- `submission.requires_reconciliation` flags uncertain submission or a `SUBMITTING` state with recorded intent. An apparently stuck `SUBMITTING` state without an intent also deserves operational investigation; do not resubmit blindly.

The pipeline tree (`GET /pipelines/{pipeline_id}/tree`) contains equivalent readiness and submission summaries on individual runs, plus `selected_run_id` per node. Its payload can be large because it currently includes full input-binding metadata.

## Select the preferred completed run

### Backward-compatible unconditional selection

```http
POST /caesar/api/v1.0/pipelines/PIPELINE_ID/nodes/flag/selection
```

```json
{"run_id": "NEW_FLAG_RUN_ID"}
```

The POST form overwrites the previous preferred run using last-writer-wins semantics. The target must belong to the node and be `COMPLETED`.

### Concurrency-safe compare-and-set selection

```http
PUT /caesar/api/v1.0/pipelines/PIPELINE_ID/nodes/flag/selection
```

```json
{
  "run_id": "NEW_FLAG_RUN_ID",
  "expected_run_id": "PREVIOUS_FLAG_RUN_ID"
}
```

The server updates the selection only if the currently selected run ID matches `expected_run_id`. Use `null` only when expecting no current selection. A conflicting update returns HTTP `409` and does not overwrite the current selection. Retrieve the latest tree or pipeline metadata and re-evaluate before trying again. For agent workflows, prefer `PUT`; reserve unconditional `POST` for deliberate overrides.

A selection change does **not** rewrite previously registered downstream runs or their frozen artifacts.

## Output retention and downstream consumption

Scientific completion, artifact registration, artifact retention, and preferred selection are independent transitions. Completion alone does not make output files available to a downstream run. Registered outputs must be retained for managed cross-stage consumption. Retention is normally handled by the configured worker; the `/retain` endpoint can queue promotion of an eligible completed run. Automatic registration/retention depends on deployment configuration.

The selected artifact and directory resolver endpoints return verified identities without exposing internal storage paths. Named-input run registration also checks availability/integrity as it freezes bindings. Do not construct source paths from pipeline or job IDs on the client.

## Errors and safe retry rules

| HTTP status | Typical meaning |
| --- | --- |
| `400` | Invalid JSON shape, identifiers, stage/input fields or forbidden combination of reference formats. |
| `401` / `403` | Missing or insufficient authentication/authorization (subject to deployment). |
| `404` | Owner-visible pipeline/run or named artifact not found. |
| `409` | State conflict: uncompleted run, stale conditional selection, absent preferred run, unretained upstream data, or already claimed submission. |
| `503` | Service/configuration problem or uncertain scheduler submission requiring investigation. |

After a submit timeout, **GET the run** and inspect `status` and `submission`. Do not repeat `/submit` automatically. If status is `SUBMISSION_UNCERTAIN`, or submission intent exists without definitive completion, use the project's existing submission reconciliation/operations procedure. A new scientific attempt should generally be represented by a new run rather than resetting an existing one-shot submission.

## Compatibility

The V2 pipeline routes are additive. Existing `/job` routes and the node-oriented `GET`/`POST /pipelines/{pipeline_id}/nodes/{node_id}/runs` contract remain available. Server-managed paths, data access, and artifact-integrity checks remain mandatory.

See [MAASAI integration guide](maasai_integration.md) for the agent workflow and the project [README](../README.md) for deployment and authentication instructions.
