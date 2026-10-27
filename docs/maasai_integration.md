# MAASAI integration with CAESAR-REST pipeline V2

This guide explains the tested R1–R3B agent-oriented CAESAR-REST contract. It describes **client orchestration**, not a server-side auto-execution engine: MAASAI chooses experiments, evaluates their scientific quality and decides which completed runs to prefer. CAESAR-REST validates, executes, retains and records the individual runs and their immutable dependencies.

For the full route reference, see [Pipeline V2 API](pipeline_v2_api.md).

## Prerequisites

1. A CAESAR-REST deployment with V2 staged execution enabled, Slurm configured, and the application/stage/input policy configured by the server administrator.
2. A service/user identity authorized to use CAESAR-REST through Keycloak/OIDC; send `Authorization: Bearer <access-token>` on API requests. Follow README deployment instructions for TLS trust.
3. An accessible managed dataset, or a completed and retained upstream run, providing valid inputs.
4. A retention worker and artifact retention root configured for cross-stage artifact binding.

All example paths below start with `/caesar/api/v1.0` and all IDs are placeholders. The OXKAT stage sequence is an **example**, not a hardcoded requirement of the pipeline framework.

## A typical agent-controlled pipeline

```text
Create pipeline
      |
Register GET_INFO (dataset input)
      |
Submit -> monitor -> COMPLETED -> artifacts READY
      |
Register 1GC with upstream named artifacts
      |
Submit -> monitor -> COMPLETED -> artifacts READY
      |
Register one or more FLAG alternatives
      |
Submit -> evaluate results -> choose preferred completed FLAG run
      |
Conditional PUT selection of FLAG preferred run
      |
Register 2GC with selected-node named artifacts
      |
Submit -> monitor -> evaluate and select as needed
```

## Step 1: Create pipeline

`POST /pipelines`

```json
{
  "app": "oxkat",
  "name": "MAASAI OXKAT optimization",
  "description": "Agent-managed alternatives for calibration and imaging"
}
```

Store the returned `pipeline_id` for subsequent calls.

## Step 2: Register a stage without submitting it

`POST /pipelines/{pipeline_id}/runs`

```json
{
  "stage": "GET_INFO",
  "dataset_id": "oxkat-test-dataset-v3"
}
```

Store `run_id` and `node_id`. For a noninitial stage, either use concrete upstream run IDs or selected-node references. For example, a downstream 2GC run:

```json
{
  "stage": "2GC",
  "node_id": "imaging_variant_a",
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

Here `flag` is a node established in the pipeline. A simplified run created without custom `node_id` uses a generic default such as `stage_flag`; the caller must reference the actual node identifier returned by the API. Custom node IDs let the agent compare multiple groups of experiments independently. `inputs` must use the exact artifact names registered for the chosen source run.

All selected-node references in one registration use one selection snapshot. The server stores explicit `source_run_id`/artifact-index bindings, and later changes to `flag` selection do not modify already registered downstream runs.

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

## Step 6: Freeze preferred artifacts into the next stage

Use `POST /pipelines/{pipeline_id}/runs` with `selected: true` named references. Check the registration response: `input_artifacts` must contain concrete upstream `source_run_id`, `source_node_id`, `artifact_index` and integrity metadata; it must not contain unresolved mutable selected-node pointers.

After registration, MAASAI may select a different preferred upstream run without affecting existing downstream runs. If a different upstream result is desired for downstream execution, create a **new downstream run**.

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

## Recommended acceptance test

On a test pipeline, create alternatives for one node and verify: registration without submission; one-shot submission; terminal-state reconciliation; registered and retained artifacts; selection with conditional `PUT`; stale `PUT` returning `409`; selected-node inputs frozen into a new downstream run; stable frozen inputs after changing the selected upstream run; and safe response to uncertain submission states. Heavy scientific stages need not be reexecuted solely to validate selection and binding semantics.

See [Pipeline V2 API](pipeline_v2_api.md) for endpoint paths and request/response examples.
