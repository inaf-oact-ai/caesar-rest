# MAASAI integration with CAESAR-REST pipeline V2


This guide describes how MAASAI can orchestrate CAESAR-REST Scientific Pipeline V2 workflows, including dataset-bound pipeline creation, scientific target discovery, bulk planning, idempotent registration, individual execution, artifact retention and preferred-run selection.

MAASAI controls scientific strategy, experiment alternatives, target selection, execution scheduling and scientific evaluation. CAESAR-REST validates and registers immutable experiments, submits individual jobs to Slurm, monitors execution, retains scientific artifacts and records provenance.

The pipeline framework does not automatically execute the next stage or select the scientifically best experiment.

This guide is an integration overview. For complete API behavior, failure recovery and idempotency rules, see the [MAASAI orchestration contract](maasai_orchestration_contract.md).

For endpoint definitions and request/response schemas, see the [Scientific Pipeline V2 REST API](api/scientific-pipelines.md).

## Prerequisites

1. A CAESAR-REST deployment with Pipeline V2 staged execution enabled, Slurm configured and the relevant application/stage/input policies activated.
2. A service or user identity authorized through Keycloak/OIDC. Protected API requests require `Authorization: Bearer <access-token>`, with TLS trust configured for the deployment.
3. An accessible managed scientific dataset registered with CAESAR-REST.
4. A completed dataset inspection with suitable scientific metadata when target discovery and target-aware bulk planning are required.
5. An artifact-retention worker and retention storage configured for downstream artifact consumption.
6. A compatible scientific application configurator, such as OXKAT, implementing the relevant Pipeline V2 stages and scientific readiness provider.

All endpoint paths in this guide are relative to `/caesar/api/v1.0`. All dataset IDs, pipeline IDs, run IDs and artifact indices appearing in examples are illustrative.

OXKAT is used as the reference application. Its scientific stages and target-specific input contracts are not hardcoded into the generic Pipeline V2 infrastructure.

## A typical agent-controlled pipeline

For an OXKAT dataset containing multiple science targets, MAASAI can orchestrate the following workflow:

```text
Discover accessible dataset
          |
Verify dataset inspection and target inventory
          |
Create dataset-bound OXKAT pipeline
          |
GET_INFO: register -> submit -> monitor -> retain -> select
          |
1GC: register -> submit -> monitor -> retain -> select
          |
POST bulk-plan (FLAG)
          |
POST bulk-register (eligible targets)
          |
          +-- Target A: FLAG -> evaluate -> select
          |
          +-- Target B: FLAG -> evaluate -> select
          |
          +-- Target C: FLAG -> evaluate -> select
          |
          +-- Target D: FLAG -> evaluate -> select
          |
POST bulk-plan (2GC)
          |
POST bulk-register (eligible targets)
          |
Independent 2GC execution, evaluation and selection
```

GET_INFO and 1GC operate using the original dataset and required upstream artifacts. FLAG and 2GC are target-specific stages.

For example, a Measurement Set may contain science targets such as MAXIJ1348, GX_339-4, J1713-4218 and EXO1846-031.

The target inventory is discovered from dataset inspection metadata; it is not supplied as a hardcoded list.

Bulk planning determines which targets have eligible upstream inputs. Bulk registration creates independent run records but does not submit jobs.

MAASAI may execute eligible targets concurrently or sequentially, according to scientific priorities and available resources.

A failed target does not require unrelated targets to restart.

After evaluating each completed run, MAASAI can select the preferred experiment for that target and proceed independently to the next stage.

Readiness checks and planning are advisory. The server revalidates inputs and artifact bindings when each run is registered.


## Step 1: Create a dataset-bound pipeline

Before creating the pipeline, identify an accessible managed dataset:

```http
GET /datasets
```

When scientific target discovery is needed, inspect the dataset and its discovered targets:

```http
GET /datasets/{dataset_id}/inspection
GET /datasets/{dataset_id}/targets
```

The inspection status should be `READY`, and the returned target metadata should be sufficiently complete for the scientific workflow.

For an OXKAT pipeline, create the dataset association through:

```http
POST /pipelines
```

Example request:

```json
{
  "app": "oxkat",
  "dataset_id": "oxkat-test-dataset-v5",
  "name": "MAASAI OXKAT optimization",
  "description": "Agent-managed calibration and imaging experiments"
}
```

The request returns HTTP `201` with the created pipeline record.

Store the returned `pipeline_id` for subsequent operations.

The dataset association is stored in the pipeline and must not be repeated when registering runs within that dataset-bound pipeline.

The server validates access to the dataset. Dataset association alone does not trigger inspection, registration or scientific execution.

For details of the inspection lifecycle and administrative refresh operation, see the [Data and datasets REST API](api/data.md).

## Step 2: Register an experiment without submitting it

**Endpoint:**

```http
POST /pipelines/{pipeline_id}/runs
```

For a dataset-bound OXKAT pipeline, register GET_INFO using:

```json
{
  "stage": "GET_INFO",
  "idempotency_key": "maasai:get-info:experiment1"
}
```

The original Measurement Set is resolved from the pipeline's dataset association according to the GET_INFO input policy.

Do not repeat `dataset_id` in the run-registration payload.

Successful registration creates an immutable run in `PLANNED` state and returns HTTP `201`.

Store the returned `run_id` and `node_id`.

The `idempotency_key` is optional for individual registration but recommended for automated clients. Persist the original request and key before sending. After an uncertain response, replay the same request unchanged rather than creating an accidental duplicate.

For 1GC, register a new run with the original dataset association and the required retained GET_INFO project information, using the input references validated by the server.

For downstream stages, supply explicit named upstream artifact references or supported selected-node references.

For example, a target-specific FLAG registration may use:

```json
{
  "stage": "FLAG",
  "node_id": "stage_flag_f1",
  "parameters": {
    "target": "MAXIJ1348"
  },
  "idempotency_key": "maasai:flag:f1:experiment1",
  "inputs": {
    "target_ms": {
      "run_id": "ONE_GC_RUN_ID",
      "artifact": "working_measurement_sets",
      "artifact_index": 3
    },
    "project_info": {
      "run_id": "GET_INFO_RUN_ID",
      "artifact": "project_info",
      "artifact_index": 8
    }
  }
}
```

The run IDs, node ID and artifact indices are illustrative.

In real use, obtain exact input references from the current scientific readiness and bulk-planning results, or from authorized registered upstream artifacts.

For OXKAT, FLAG consumes a calibrated target Measurement Set from 1GC and compatible project information.

The 2GC stage requires the corresponding flagged target Measurement Set, compatible project information and eligible FLAG imaging products.

The server validates stage-specific input bindings before registration.

When an input uses a selected-node reference, CAESAR-REST resolves it to a concrete upstream run and artifact identity during registration.

The resulting immutable `input_artifacts` record stores the resolved source run and artifact indices. Later changes to upstream preferred-run selections do not modify this binding.

Registration never submits a Slurm job.


## Target-aware bulk planning and registration

MAASAI can use bulk planning and registration to manage several independent science targets.

These operations are particularly useful after a selected 1GC run has produced retained, target-specific Measurement Sets.

### Discover stage readiness

**Endpoint:**

```http
GET /pipelines/{pipeline_id}/scientific-readiness
```

The response provides application-specific scientific readiness based on the dataset inspection metadata, current preferred upstream runs and available retained artifacts.

For OXKAT, it describes the discovered science targets and their readiness for FLAG and 2GC.

A target may be blocked because required upstream products are missing, incomplete, unavailable or ambiguous.

### Plan eligible targets

**Endpoint:**

```http
POST /pipelines/{pipeline_id}/bulk-plan
```

Example:

```json
{
  "stage": "FLAG",
  "targets": [
    "MAXIJ1348",
    "GX_339-4"
  ]
}
```

The `targets` filter is optional. When omitted, the OXKAT provider considers all discovered science targets.

The response contains a target-specific `items` array.

Each item includes:

- `field_id`: scientific field identity.
- `target`: target name.
- `can_register`: whether a registration proposal is available.
- `blocking_reasons`: reasons preventing registration.
- `registration`: complete proposed registration payload, or null.

The overall planning status can be `READY` even when some targets are blocked. MAASAI must check each item's `can_register` value.

Planning does not create runs, reserve inputs or execute scientific processing.

### Register eligible proposals

**Endpoint:**

```http
POST /pipelines/{pipeline_id}/bulk-register
```

The request contains between 1 and 32 registration items.

Each item contains:

- `idempotency_key`: unique, stable registration identity.
- `registration`: the exact, unchanged proposal returned by bulk planning.

For illustration, the request envelope is:

```json
{
  "items": [
    {
      "idempotency_key": "maasai:flag:f1:experiment1",
      "registration": {
        "stage": "FLAG",
        "node_id": "stage_flag_f1",
        "parameters": {
          "target": "MAXIJ1348"
        },
        "inputs": {
          "target_ms": {
            "run_id": "ONE_GC_RUN_ID",
            "artifact": "working_measurement_sets",
            "artifact_index": 3
          },
          "project_info": {
            "run_id": "GET_INFO_RUN_ID",
            "artifact": "project_info",
            "artifact_index": 8
          }
        }
      }
    }
  ]
}
```

This example is illustrative. Actual artifact identities must come directly from the latest applicable planner proposal.

For first-time registration, CAESAR-REST recomputes scientific readiness and requires the submitted proposal to match the current one exactly.

The response uses three per-item status values:

| Status | Meaning |
| --- | --- |
| `CREATED` | A new run was registered |
| `REPLAYED` | An identical registration already exists |
| `FAILED` | This item was not successfully registered |

Bulk registration may partially succeed.

HTTP `200` indicates that the request envelope was processed, not that all items were successfully registered.

MAASAI must inspect `summary.failed` and every item result.

For `CREATED` and `REPLAYED`, store or reuse the returned run ID. A replayed run may already be executing or completed.

For `FAILED`, inspect the per-item error and determine whether the target requires replanning or another explicit recovery action.

### Registration recovery and scientific alternatives

Persist the complete registration object and idempotency key before sending the request.

If the HTTP result is uncertain, retry the same registration with the same key and unchanged payload.

Do not reuse a key with changed inputs or scientific parameters.

A new scientific experiment requires a new registration identity.

Bulk registration accepts the planner's unchanged default proposals. To explore alternative scientific parameters, use individual run registration with an explicit `node_id`, validated inputs and a new idempotency key.

For OXKAT, these alternatives can specify stage-compatible `oxkat_config` overrides.

Bulk registration does not submit runs automatically. MAASAI must explicitly submit each registered run using the individual submission endpoint.

For comprehensive recovery semantics, see the [MAASAI orchestration contract](maasai_orchestration_contract.md).

## Step 3: Submit once

`POST /pipelines/{pipeline_id}/runs/{run_id}/submit` with `{}`.

Keep the returned `job_id` if available. A submission request is one-shot for the reserved run; never blindly retry after an HTTP timeout. The claim and durable submission intent protect against duplicate Slurm submissions.

## Step 4: Observe run state, not just job completion

`GET /pipelines/{pipeline_id}/runs/{run_id}`; use the tree endpoint to inspect several runs at once.

Read the following fields separately:

| Field | Agent decision |
| --- | --- |
| `status` | Is the scientific run `PLANNED`, active, `COMPLETED` or failed? |
| `submission.state` | Was a scheduler submission started, accepted, failed or uncertain? |
| `submission.retry_allowed` | Does the stored lifecycle allow an initial submission? Not automatic retry authority after a timeout. |
| `submission.requires_reconciliation` | Is an uncertain submission or durable intent present? Escalate to reconciliation. |
| `readiness.can_select` | May MAASAI make this completed experiment preferred? |
| `readiness.can_consume` | Does persisted retention metadata indicate this run's full artifact set is available for downstream binding? |
| `selected` | Does this run currently match the node's preferred run pointer? |

`COMPLETED` does not imply retained/consumable outputs. `submission.state=ACCEPTED` also does not imply scientific success. `can_consume` is metadata-derived and stage-independent; actual downstream binding validates retained artifacts and integrity before creating the next run.

If a run completes but output retention is pending, continue observing readiness; do not try to create a downstream run from unretained files. The authenticated `/retain` endpoint can request eligible output retention if the configured worker has not already queued it.

## Retrieve scientific products for evaluation

After an experiment completes, MAASAI may need to inspect scientific outputs before deciding whether the run is acceptable or whether another experiment should be registered.

The application self-description lists the scientific products that an application may generate:

```http
GET /app/{app_name}/describe
```

For OXKAT, these declarations include project metadata, calibration tables, diagnostic plots, imaging products, execution scripts and logs.

The self-description does not guarantee that every declared output is present in every run.

To discover the actual products registered for a completed run:

```http
GET /pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/artifacts
```

The response lists registered output artifacts and their metadata, including artifact indices and available type and role information.

For an eligible regular-file artifact, MAASAI can request:

```http
GET /pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/artifacts/{index}
```

The server verifies the request against the registered run and applicable artifact-access rules.

Directory artifacts cannot currently be downloaded through the regular-file endpoint.

This limitation is important for OXKAT because calibration and imaging diagnostics are often grouped within directory artifacts.

MAASAI must not construct filesystem paths to retrieve files directly from execution workspaces or retained-artifact storage.

### Scientific assessment

MAASAI is responsible for interpreting the available products and evaluating scientific quality.

An evaluation workflow may include:

1. Inspect the run status and artifact inventory.
2. Identify available diagnostic products relevant to the scientific stage.
3. Retrieve accessible files through the authenticated artifact API.
4. Evaluate the results against application-specific scientific criteria.
5. Accept the result or register a new experiment with modified scientific parameters.
6. Select the preferred completed run when the evaluation supports that decision.

The precise diagnostic products and quality thresholds needed for OXKAT calibration and imaging assessment are not yet defined as a complete machine-readable contract.

These requirements will be reviewed with astronomers during the final integration milestone.

Any future artifact-discovery or retrieval extensions should preserve authorization, provenance and the integrity of retained upstream products.

## Step 5: Compare alternatives and select safely

MAASAI performs scientific evaluation outside CAESAR-REST, then reads the current `selected_run_id` from `GET /pipelines/{pipeline_id}/tree` or pipeline metadata.

`PUT /pipelines/{pipeline_id}/nodes/{node_id}/selection`

```json
{
  "run_id": "NEW_PREFERRED_RUN_ID",
  "expected_run_id": "PREVIOUS_SELECTED_RUN_ID"
}
```

If there is no selected run, use `"expected_run_id": null` (JSON null). The selected run must be `COMPLETED`; retaining its output is not required for the selection operation itself.

A `409` means the expected selection was stale or another state conflict occurred. Refresh the current selection and reconsider the scientific decision. Do not force-overwrite another agent's selection without coordinating. The backward-compatible `POST` endpoint is unconditional and is best reserved for deliberate manual overrides.

## Step 6: Select upstream results and plan the next stage

After evaluating a completed experiment, MAASAI may update the preferred run for the corresponding node.

Preferred-run selection is scoped to the node, not to the entire scientific stage.

Before planning dependent work, ensure that the selected upstream run has the required registered and retained outputs.

The run's `readiness.can_consume` field provides a metadata-based readiness indication. Authoritative input verification occurs when downstream runs are registered.

### Target-specific progression

For OXKAT, after selecting the preferred FLAG results, MAASAI should refresh:

```http
GET /pipelines/{pipeline_id}/scientific-readiness
```

Then request new 2GC proposals:

```http
POST /pipelines/{pipeline_id}/bulk-plan
```

Example:

```json
{
  "stage": "2GC"
}
```

The planner evaluates each discovered target independently.

A target with suitable selected and retained FLAG products may be eligible for 2GC, while another target remains blocked.

The 2GC proposal contains concrete references to the required upstream artifacts, including the target Measurement Set, compatible project information and FLAG imaging product.

MAASAI should register only eligible targets and submit each new run individually.

### Immutable downstream bindings

When a downstream run is registered, CAESAR-REST resolves its upstream inputs and freezes their concrete identities.

The registered `input_artifacts` metadata includes source run identities, artifact indices and integrity-related metadata.

After registration, changing the preferred upstream run does not modify existing downstream bindings.

If MAASAI wishes to use a different upstream result, it must register a new downstream experiment.

This guarantees that the provenance of an already registered experiment remains stable across later changes to preferred-run selections.

For alternative scientific configurations, use individual run registration with a new idempotency key rather than modifying a previously registered run.

## Safe submit-timeout handling

Recommended client flow:

1. Submit an existing `PLANNED` run once.
2. If the HTTP response is lost or times out, call `GET /pipelines/{pipeline_id}/runs/{run_id}`.
3. For `SUBMITTED`, `RUNNING`, `COMPLETED`, `FAILED` or `CANCELLED`, treat the original submission as already accepted and continue monitoring/evaluating.
4. For `SUBMISSION_UNCERTAIN`, stop and request operator-assisted reconciliation; do not resubmit.
5. For `SUBMITTING`, do not issue another submit request. Continue normal observation or investigate a stalled submission; a recorded intent may already have contacted Slurm.
6. For `SUBMISSION_FAILED`, inspect the failure and create a new run for a new attempt where appropriate. Existing one-shot intent behavior must not be bypassed.
7. If the run still appears `PLANNED` after a timeout, it may mean the request never reached the server, but do not assume this without establishing the earlier request's outcome. The authoritative atomic server claim remains the duplicate-submission guard.

The public `submission.retry_allowed` field is a lifecycle indicator and cannot make an ambiguous HTTP retry safe by itself.

## Access, integrity and operational boundaries

- Never fabricate paths to upstream job directories or retained artifacts. Use server-managed bindings and artifact resolvers.
- Do not submit data paths, shell commands or unapproved scientific options through simplified run creation; all execution parameters must satisfy the server-side application policy.
- Only owner-scoped, completed and artifact-registered upstream runs may supply named inputs. Retained file and directory integrity is verified at binding time.
- The agent can select completed runs before retention finishes; it should wait for consumable outputs before registering dependent stages.
- A pipeline can contain many runs for a stage, separate experimental nodes and a mutable selection per node. No server route automatically picks the scientifically best run.
- The tree response currently contains verbose frozen input bindings; use individual run retrieval for detailed inspection and avoid treating the tree as a compact pagination API.

## Recommended integration acceptance tests

A complete MAASAI integration regression should validate both the generic Pipeline V2 behavior and the application's scientific branching workflow.

Recommended scenarios include:

1. Create an accessible managed dataset and verify its inspection metadata.
2. Create a dataset-bound pipeline with the appropriate application.
3. Register an initial run without repeating `dataset_id`.
4. Verify registration creates a `PLANNED` run without submitting a job.
5. Exercise explicit one-shot submission and persisted submission-state reporting.
6. Verify output registration, retention and consumability.
7. Query scientific readiness and confirm correct target identities and stage prerequisites.
8. Bulk-plan all targets and selected target subsets.
9. Bulk-register eligible proposals and confirm independent run records and immutable bindings.
10. Replay identical registrations and verify that the original run IDs are returned.
11. Exercise stale proposals, idempotency-key conflicts and partial bulk-registration failures.
12. Verify that failures affecting one target do not prevent unrelated targets from progressing.
13. Evaluate completed runs and update preferred-run selections through conditional `PUT`.
14. Confirm that downstream planning uses the correct selected, retained target-specific artifacts.
15. Verify that changing an upstream selection does not alter existing downstream input bindings.
16. Verify run and artifact access restrictions across different authenticated owners.
17. Inspect registered scientific evaluation products and verify supported artifact retrieval paths.
18. Confirm safe client behavior after uncertain submission responses.

Lightweight synthetic scientific outputs should be used where practical to avoid repeatedly executing computationally expensive OXKAT stages.

A separate deployment-level test should verify the configured Keycloak authentication, MongoDB persistence, Slurm execution, artifact-retention worker and scientific container integration.

The final scientific acceptance review must also verify the diagnostic products and quality criteria needed for MAASAI to evaluate OXKAT runs and select preferred experiments.

The lightweight R4C.3.3 compatibility tests do not by themselves establish that this full end-to-end workflow has passed.

## Further documentation

- [Scientific Pipeline V2 REST API](api/scientific-pipelines.md)
- [Data and dataset inspection REST API](api/data.md)
- [Application discovery and self-description](api/applications.md)
- [MAASAI Pipeline V2 orchestration contract](maasai_orchestration_contract.md)
- [Pipeline artifact retention](deployment/artifact-retention.md)
