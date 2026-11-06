# MAASAI ↔ CAESAR-REST Pipeline V2 orchestration contract

**Status:** R4C.3.3 orchestration contract completed and locally validated on
2026-11-04. Pipeline V2 artifact retrieval by explicit run, selected run,
name, path and index has subsequently been implemented, tested and
deployment-validated in November 2026. Scientific run evaluation and
MAASAI-side comparison logic remain separate integration activities.

**Base URL:** `/caesar/api/v1.0`

**Authentication:** `Authorization: Bearer <access-token>` (Keycloak/OIDC).
All pipeline and artifact operations are owner-scoped.

## 1. Ownership and invariants

**MAASAI** decides when to run stages, target subsets, concurrency, scientific parameters, evaluation criteria, experiment comparison, retries as *new experiments*, and preferred selections. **CAESAR-REST** authorizes dataset/pipeline access, validates input policy, registers immutable runs, binds retained artifacts, submits a single run to Slurm, tracks lifecycle, retains outputs, and implements conditional preferred-run selection. No endpoint automatically advances the pipeline.

- A **pipeline** is dataset-bound via its top-level `dataset_id`; the stage determines whether `run.dataset_id` is populated. For OXKAT GET_INFO and 1GC, the dataset supplies `measurement_set`; FLAG and 2GC use retained upstream artifacts and do not use a separate run-level dataset binding.
- A **node** groups alternative experiments. A selected run is a mutable pointer scoped to one node, **not** to the whole stage. The OXKAT planner uses `stage_flag_f<field_id>` and `stage_2gc_f<field_id>`.
- A **run** is an immutable execution reservation, with frozen `input_artifacts`. Run registration does not submit anything.
- `COMPLETED` alone does not mean consumable. Wait for retained artifacts and `readiness.can_consume` before downstream registration; binding verification remains authoritative.
- Scientific readiness describes target/stage prerequisites; generic readiness describes selected-run and artifact metadata. Both are snapshots, not reservations.
- All `POST /bulk-plan` responses are advisory; `POST /bulk-register` recomputes readiness and insists on an **exactly matching** current proposal for first-time registration.

## 2. Endpoints MAASAI uses

Paths are relative to the base URL.

| Method | Path | Contract |
| --- | --- | --- |
| `POST` | `/pipelines` | Create dataset-bound pipeline; specify `app`, `dataset_id`, optional metadata |
| `GET` | `/pipelines/{pid}` | Pipeline metadata, current selections |
| `GET` | `/pipelines/{pid}/tree` | All registered runs by node, selected run IDs, immutable inputs |
| `GET` | `/pipelines/{pid}/readiness` | Generic selected-run readiness |
| `GET` | `/pipelines/{pid}/scientific-readiness` | Provider-specific target and stage readiness |
| `POST` | `/pipelines/{pid}/bulk-plan` | Read-only target planning for configured stage |
| `POST` | `/pipelines/{pid}/bulk-register` | Register up to 32 unmodified plan proposals with per-item idempotency keys |
| `POST` | `/pipelines/{pid}/runs` | Register an individual run, optionally with `idempotency_key` |
| `GET` | `/pipelines/{pid}/runs/{rid}` | Current run status, submission state, readiness, selection |
| `POST` | `/pipelines/{pid}/runs/{rid}/submit` | One-shot execution submit; JSON `{}` |
| `POST` | `/pipelines/{pid}/sync` | Explicit job-state synchronization when required |
| `POST` | `/pipelines/{pid}/nodes/{nid}/runs/{rid}/retain` | Queue eligible output retention |
| `PUT` | `/pipelines/{pid}/nodes/{nid}/selection` | Compare-and-set preferred completed run |
| `GET` | `/pipelines/{pid}/nodes/{nid}/runs/{rid}/artifacts` | Inspect registered outputs |
| `GET` | `/pipelines/{pid}/nodes/{nid}/runs/{rid}/artifacts/{index}` | Download a registered file from a specific run by stable index |
| `GET` | `/pipelines/{pid}/nodes/{nid}/runs/{rid}/artifacts/by-name/{name}` | Download a uniquely named file from an explicit run |
| `GET` | `/pipelines/{pid}/nodes/{nid}/runs/selected/artifacts/by-name/{name}` | Download a uniquely named file from the currently selected run |
| `GET` | `/pipelines/{pid}/nodes/{nid}/runs/{rid}/artifacts/by-path?relative_path={path}` | Download an exact registered file from an explicit run |
| `GET` | `/pipelines/{pid}/nodes/{nid}/runs/selected/artifacts/by-path?relative_path={path}` | Download an exact registered file from the selected run |
| `GET` | `/pipelines/{pid}/nodes/{nid}/selected/artifacts/{name}` | Resolve selected-run file metadata without downloading |

There is **no bulk-submit** endpoint and **no automatic scientific evaluator**. MAASAI submits each registered run individually, with explicit scheduling/concurrency policy.

### Artifact retrieval and evaluation contract

MAASAI may access registered artifacts of an authorized completed run
without making that run the node's preferred selection.

The preferred-run pointer is an orchestration decision, not an artifact
access-control boundary.

For scientific experiment comparisons, MAASAI SHOULD:

1. Use explicit `run_id` values for all evaluation requests.
2. Retrieve each candidate run's registered artifact inventory.
3. Download uniquely named QA products using `by-name`.
4. Download individual members of repeated artifact families using
   `by-path` or their registered numeric indices.
5. Preserve the concrete run and artifact identifiers used for evaluation.
6. Select a preferred run only after the comparison is complete.

The `selected` alias is a late-bound convenience reference and may
resolve to a different run after a selection update.

An artifact name that matches multiple registered files is ambiguous
and returns HTTP `409`.

The download endpoints support registered regular files only.
Scientific directory artifacts remain accessible through the managed
downstream-binding mechanism, not general HTTP directory download.

A completed run may have registered artifacts before retention completes.
The available artifact-download implementation performs its normal
access and integrity checks; downstream consumers must still respect
artifact readiness and binding validation.

CAESAR-REST does not rank scientific experiments or choose their
preferred outputs. MAASAI retains responsibility for scientific evaluation.

## 3. OXKAT workflow across four science targets

```text
Dataset inspection READY (four science targets)
     |
     +-- GET_INFO: register -> submit -> monitor -> retain -> select
     |
     +-- 1GC: register using dataset and selected GET_INFO project_info
                 -> submit -> monitor -> retain -> select
                    |
                    +-- POST bulk-plan {"stage":"FLAG"}
                    +-- POST bulk-register for chosen plannable targets
                    +-- submit FLAG run for each target (independently)
                    +-- monitor, retain, evaluate, select preferred FLAG per target/node
                           |
                           +-- POST bulk-plan {"stage":"2GC"}
                           +-- POST bulk-register plannable target proposals
                           +-- submit/monitor/retain/evaluate 2GC independently
```

The planner returns `field_id`, `target`, `can_register`, `blocking_reasons`, and `registration`. Store target identity (`field_id` and `target`) alongside the generated `node_id` and `run_id`. Do not assume arrays are ordered in scientific priority or that the target name alone provides a globally unique identity across datasets.

### Example: discover next-stage work

`POST /pipelines/{pid}/bulk-plan`

```json
{"stage":"FLAG","targets":["MAXIJ1348","GX_339-4"]}
```

If `can_register` is false, no `registration` exists; record blocking reasons and do not attempt to register it. Top-level `status:"READY"` means the *planner* operated successfully, not that every target is plannable. With `NO_CONSUMABLE_1GC_TARGET_INPUTS` wait for selected, retained 1GC results.

### Example: register unchanged proposals

Use the **exact** `registration` object returned by the latest planner response:

```json
{
  "items": [
    {
      "idempotency_key": "maasai:job42:flag:f1:attempt1",
      "registration": {
        "stage": "FLAG",
        "node_id": "stage_flag_f1",
        "parameters": {"target": "MAXIJ1348"},
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

`ONE_GC_RUN_ID`, `GET_INFO_RUN_ID`, and the target-MS index are **illustrative**. Copy actual values from `bulk-plan`; never assume artifact indices. A bulk request may contain up to 32 items, and may not repeat a key or a `(stage,target)` pair. Several individual items can succeed while others fail.

For each returned item:

- `CREATED`: persist `run_id`, `node_id`, idempotency key, registration fingerprint and status; schedule later submission if desired.
- `REPLAYED`: reuse the returned **existing** run ID; it may now be `SUBMITTED`, `RUNNING` or terminal. Do **not** infer that it is still `PLANNED`.
- `FAILED`: inspect `http_status` and `error`; successful siblings remain registered. A blocked or stale proposal should be replanned. A 409 idempotency-key conflict means the same key cannot be used for a changed registration.

A bulk HTTP 200 is **not** evidence all items were registered: always check `summary.failed` and each item status. The endpoint does not provide all-or-nothing transactions.

## 4. Experiment alternatives and selections

Bulk planning emits the provider's default per-target proposal, and bulk registration requires an exact match to the current proposal. **It is not currently a mechanism to generate arbitrary scientific parameter alternatives.** To explore a different `oxkat_config` or other permitted parameters, use `POST /pipelines/{pid}/runs` with an explicit `node_id` and required explicit input references; use a **new** idempotency key for each new experiment. Group alternatives for the *same target and stage* under the same node if MAASAI will select one preferred run among them. Preserve `parameters.target` and the scientific provider's expected lineage.

After a run completes and is evaluated:

1. Read the current selection from pipeline metadata or tree (`selected_run_id`).
2. Verify the intended run is `COMPLETED`; preferably wait until its artifacts are consumable before driving a dependent stage.
3. `PUT /pipelines/{pid}/nodes/{nid}/selection`:

```json
{"run_id":"NEW_PREFERRED_RUN_ID","expected_run_id":null}
```

Replace null with the actual currently selected ID when one exists. A 409 means a competing selection or other conflict: reload and make a new scientific decision. Do not force the unconditional selection API from an automated MAASAI workflow.

**Important:** a selection pointer is per node. The scientific provider will inspect the selected, consumable upstream nodes and target bindings; for alternative nodes or multiple selected candidates, inspect `/scientific-readiness` and `/bulk-plan` for `AMBIGUOUS_UPSTREAM_INPUTS` rather than guessing which one to consume.

## 5. Independent lifecycle and recovery

### Registration retry

Persist the **original registration JSON** and a stable idempotency key before sending. Reuse both unchanged after a network timeout; the server's unique partial index ensures at most one persisted run for `(owner,pipeline_id,key)`. A replay may succeed after an upstream selection changes because it returns the original committed reservation. For a *new* scientific attempt, generate a new key.

A retry after no commit may encounter newly changed readiness; obtain a fresh plan and use a **new** key if the registration object changes. Never intentionally reuse a key with a different request.

### Submission retry is different

Registration idempotency does **not** make job submission freely retryable. Submit only a `PLANNED` run once via `POST /runs/{rid}/submit` using `{}`. If the HTTP outcome is lost, inspect `GET /runs/{rid}` and its `submission` record. `SUBMITTING` or `SUBMISSION_UNCERTAIN` requires observation/reconciliation, not blind resubmission; `submission.retry_allowed` is not permission to repeat an ambiguous request. For a fresh experiment after `SUBMISSION_FAILED` or failed science, register a new run with a new key.

### Retention, selection and downstream registration

`COMPLETED` is not equivalent to `readiness.can_consume`. If artifacts are registered but not yet retained, wait for the worker or request retention through `/retain`. Select the preferred run via conditional PUT; then re-query scientific readiness and bulk-plan. New downstream registrations freeze source `run_id` and artifact indices. Changing upstream selection does not rewrite previously registered downstream runs.

### Partial failure policy

One target's registration, submission, scientific failure or artifact-retention failure must not cancel unrelated targets. MAASAI should maintain a per-target state map keyed by `(pipeline_id, stage, field_id, node_id)` with current desired experiment, registration key, run ID, lifecycle and latest blocking reason. The state map belongs to MAASAI; the REST service remains the source of truth for run records and selections.

## 6. Suggested MAASAI orchestration state machine

`DISCOVERED -> BLOCKED | PLANNABLE -> REGISTERED -> SUBMITTING -> SUBMITTED/RUNNING -> COMPLETED -> RETAINED -> EVALUATED -> SELECTED -> DOWNSTREAM_PLANNABLE`

`FAILED`, `SUBMISSION_FAILED`, `SUBMISSION_UNCERTAIN`, and retention failures are distinct recovery branches; do not collapse them into one retry path. This state machine is a **client-side recommendation**, not a new CAESAR-REST persisted status enum.

## 7. Recommended acceptance tests

1. Create a disposable dataset-bound pipeline and complete GET_INFO/1GC with retained test outputs in an isolated environment.
2. Verify `scientific-readiness` returns four targets and correct stage blocking/consumability.
3. Bulk-plan FLAG for all and a subset. Verify exact `registration` identities and all reported blocking reasons.
4. Bulk-register two valid proposals. Verify two `PLANNED` runs with distinct target nodes and frozen bindings; submit **neither** automatically.
5. Repeat identical bulk registration: both `REPLAYED` with identical run IDs, even after changing an upstream selection.
6. Reuse a key with different inputs: per-item `FAILED` with 409. Replan stale input before first registration: per-item failure without creating a run.
7. Exercise mixed success and failure; verify successes persist and HTTP 200 alone is not treated as full success.
8. Submit one `PLANNED` run explicitly; inspect its persisted submission lifecycle. Never replay an uncertain submit automatically.
9. Select two different completed FLAG target nodes; confirm 2GC planning uses each target's own FLAG product and blocks any target still missing eligible inputs.
10. Verify another owner cannot read or register into the pipeline; verify retention, artifact integrity and dataset provenance.

## 8. Explicit limitations of the current contract

- There is **no bulk execution** API, server-side auto-advance, priority queue or automatic scientific optimization engine.
- Bulk registration does not support modified planner proposals or arbitrary extra scientific configuration; use single-run registration for alternatives.
- Up to 32 registrations per bulk request; larger target sets require batches. Partial failures are expected behavior.
- Planning/readiness are metadata snapshots; a successful plan is not a reservation or guarantee of later registration.
- MongoDB idempotent registration protects persisted run identity; the Slurm submission lifecycle has separate one-shot safety requirements.
- No end-to-end physical OXKAT multi-target run has yet been validated by the tests described here. This remains part of R4C.4.

## 9. Milestone R4C.3.3 completion and validation

**Status: COMPLETE — 2026-11-04**

The MAASAI ↔ CAESAR-REST Pipeline V2 orchestration contract has been defined and reviewed against the `devel` implementation.

The contract establishes:

- The separation of responsibilities between MAASAI and CAESAR-REST.
- The API sequence for dataset-bound pipeline creation, scientific readiness, bulk planning, controlled bulk registration, individual execution, monitoring, retention, and preferred-run selection.
- Independent orchestration and recovery of target-specific scientific processing branches.
- Idempotency-key lifecycle and recovery after uncertain registration responses.
- One-shot Slurm submission semantics and reconciliation of uncertain submission outcomes.
- Immutable upstream artifact bindings and conditional preferred-run selection.

The five lightweight compatibility tests in `tests/test_maasai_contract.py` passed on the local `devel` environment.

These tests validate public route availability and selected bulk planning/registration request validation rules. They do not constitute end-to-end deployment or scientific execution tests.

The following activities are assigned to **R4C.4**:

1. End-to-end integration regression of the MAASAI-style orchestration workflow, including independent multi-target processing.
2. Deployment-level validation involving authentication, MongoDB, Slurm, and artifact retention.
3. Consolidation and correction of the public CAESAR-REST REST API documentation, including dataset binding, dataset inspection, scientific readiness, bulk planning, and bulk registration.
4. Review of intermediate scientific product discovery, retrieval, and download capabilities needed for MAASAI-driven run evaluation.
5. Definition of scientific evaluation product requirements in consultation with astronomers.

No new automatic pipeline execution or scientific optimization functionality is introduced by R4C.3.3.
