# Scientific Pipeline V2 REST API

CAESAR-REST provides an authenticated REST API for registering, executing, monitoring and managing multi-stage scientific workflows.

Scientific Pipeline V2 extends the existing job execution infrastructure with experiment registration, immutable input bindings, preferred-run selection, artifact retention and safe asynchronous submission.

The pipeline infrastructure is **application-independent**. Scientific stages, input requirements, supported parameters, output artifacts and execution configuration are defined by server-side application configurators.

The examples in this guide use **OxKAT**, a radio-interferometric data-processing pipeline, but the architecture also supports other scientific applications.

## 1. API conventions

All pipeline endpoints use the base path:

```text
/caesar/api/v1.0
```

Pipeline operations require an authenticated identity. REST clients supply a valid OAuth 2.0 access token:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

Pipeline records, runs, selections and artifacts are scoped to the authenticated owner. An upstream run belonging to a different owner or pipeline cannot be bound as an input.

Identifiers such as `PIPELINE_ID`, `RUN_ID` and `DATASET_ID` in the examples are placeholders.

For general authentication conventions, see [REST API overview](overview.md) and [Keycloak and OpenID Connect authentication](../deployment/authentication.md).

## 2. Architecture and concepts

Scientific Pipeline V2 separates the logical description of an experiment from execution of the corresponding scientific job.

| Concept | Description |
| --- | --- |
| **Pipeline** | Owner-scoped collection of scientific experiments and execution history, optionally associated with a managed dataset through a pipeline-level `dataset_id` |
| **Stage** | Scientific processing operation validated by the application |
| **Node** | Logical group of alternative runs, normally associated with a stage |
| **Run** | Registered experiment with fixed scientific parameters and input dependencies |
| **Selection** | Mutable pointer identifying the preferred completed run of a node |
| **Artifact** | Registered scientific output file or directory |
| **Artifact binding** | Immutable downstream reference to an upstream artifact |
| **Retention** | Copying and verification of outputs in managed long-lived artifact storage |
| **Submission intent** | Durable record used to protect a run against duplicate scheduler submission |

### Dataset-bound pipelines

A Pipeline V2 instance can be associated with a managed scientific dataset at creation time by specifying `dataset_id` in the pipeline creation payload.

The dataset association is stored in the pipeline record and is authoritative for subsequent run registration.

For a dataset-bound pipeline:

- The dataset must exist and be accessible to the authenticated caller.
- Individual run-registration requests must not repeat `dataset_id`.
- The application and stage input policies determine whether the registered dataset is consumed directly.
- Downstream stages may consume retained upstream artifacts instead of the original dataset.
- Dataset inspection metadata can support scientific readiness and target-specific planning.

For example, an OXKAT pipeline is associated with an original MeerKAT Measurement Set. GET_INFO and 1GC consume the registered dataset according to their stage input policies, while FLAG and 2GC consume retained artifacts produced by earlier stages.

The pipeline-level dataset association must not be confused with the resolved dataset input stored in an individual run record. A downstream run can have no direct dataset input while still belonging to a dataset-bound pipeline.

For compatibility, the legacy run-registration implementation can still accept `dataset_id` for pipelines without a dataset association, subject to application input policies. New clients should use dataset-bound pipeline creation when supported.

### Pipeline stages and nodes

A stage identifies a scientific operation. For example, an OxKAT workflow may include:

```text
GET_INFO -> 1GC -> FLAG -> 2GC
```

A node groups alternative experiments associated with a scientific stage.

For example, two nodes may represent separate strategies for flagging:

```text
flag_conservative
flag_aggressive
```

Each node maintains its own preferred-run selection.

When `node_id` is omitted during simplified run registration, CAESAR-REST derives a generic node ID such as `stage_flag` or `stage_2gc`.

A pipeline may therefore contain multiple nodes for the same scientific stage.

### Runs and immutable experiments

A run represents one registered scientific experiment.

Its scientific parameters and input dependencies are fixed when the run is created. Registration does not immediately submit a scheduler job.

Clients can register alternative runs, execute them independently and compare their results.

### Preferred-run selection

Each node can identify one completed run as its preferred result.

Selection is mutable: a client may change its preference after comparing alternative experiments.

However, **changing a preferred selection does not modify previously registered downstream runs**.

When a downstream run is registered, the server resolves its upstream references and freezes their artifact identities.

This ensures that downstream experiments continue to consume the intended upstream results even when preferences change.

## 3. Execution and artifact lifecycle

Scientific execution and artifact management are separate lifecycle operations.

A typical dataset-bound scientific workflow is:

1. Register or identify an accessible managed scientific dataset.
2. Create a pipeline associated with that dataset.
3. Inspect the dataset when scientific target discovery is required.
4. Register an initial scientific run using validated stage parameters and inputs.
5. Submit the registered run explicitly.
6. Monitor execution until scientific completion.
7. Register and retain its output artifacts.
8. Evaluate completed runs and optionally select a preferred result.
9. Query generic and scientific readiness for downstream execution.
10. Plan and register downstream runs, individually or through bulk registration when supported.
11. Submit and monitor each registered downstream run independently.
12. Repeat until the desired scientific workflow is complete.

Pipeline creation, dataset inspection, readiness checks, planning, registration and submission are distinct operations.

In particular:

- Readiness checks do not create runs.
- Bulk planning does not create runs or submit jobs.
- Bulk registration creates independent run records but does not submit jobs.
- Run submission is an explicit one-shot operation.
- Scientific evaluation and preferred-run selection remain client decisions.
- CAESAR-REST does not automatically advance a completed run to the next scientific stage.


### Scientific completion versus artifact readiness

A scientifically completed run is not necessarily ready to supply inputs to a downstream stage.

CAESAR-REST distinguishes:

- **Scientific execution status**, indicating whether the run completed.
- **Artifact registration**, identifying the files or directories produced.
- **Artifact retention**, preserving those outputs in managed storage.
- **Artifact readiness**, indicating whether retained metadata is available.
- **Input-binding validation**, verifying the specific artifacts required by a downstream run.

A completed run may be selected before retention finishes, but **downstream stages require registered, retained and validated upstream artifacts**.

The run-readiness response provides useful summary information; the binding layer remains authoritative when a new downstream run is registered.

### Execution infrastructure

Pipeline V2 reuses CAESAR-REST job execution and monitoring infrastructure.

The current staged pipeline implementation targets the configured Slurm execution backend. Application-specific staged execution also depends on deployment configuration.

The artifact-retention worker is separate from the REST request handler and job-monitoring process.

Retention requests queue work; they do not perform potentially large filesystem copies synchronously inside an HTTP request.

See [Slurm deployment](../deployment/slurm.md), [Job monitoring](../deployment/job-monitoring.md) and [Artifact retention](../deployment/artifact-retention.md).

## 4. REST endpoint reference

All paths in the following tables are relative to `/caesar/api/v1.0`.

### 4.1 Pipelines and runs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/pipelines` | Create a pipeline |
| `GET` | `/pipelines` | List owner-visible pipelines |
| `GET` | `/pipelines/{pipeline_id}` | Retrieve pipeline metadata and selections |
| `GET` | `/pipelines/{pipeline_id}/runs` | List runs across the pipeline |
| `POST` | `/pipelines/{pipeline_id}/runs` | Register a simplified V2 run |
| `GET` | `/pipelines/{pipeline_id}/runs/{run_id}` | Retrieve run details, readiness and submission information |
| `POST` | `/pipelines/{pipeline_id}/runs/{run_id}/submit` | Submit a previously registered run |
| `GET` | `/pipelines/{pipeline_id}/tree` | Retrieve the pipeline execution tree |
| `POST` | `/pipelines/{pipeline_id}/sync` | Reconcile run states against persisted job information |
| `GET` | `/pipelines/{pipeline_id}/readiness` | Retrieve generic pipeline and selected-run readiness |
| `GET` | `/pipelines/{pipeline_id}/scientific-readiness` | Retrieve application-specific scientific readiness |
| `POST` | `/pipelines/{pipeline_id}/bulk-plan` | Produce read-only target-specific registration proposals |
| `POST` | `/pipelines/{pipeline_id}/bulk-register` | Register multiple validated proposals with per-item idempotency |

### 4.2 Node-oriented and selection operations

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs` | List runs belonging to a node |
| `POST` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs` | Register a run through the legacy-compatible node-oriented contract |
| `POST` | `/pipelines/{pipeline_id}/nodes/{node_id}/selection` | Unconditionally select a completed run |
| `PUT` | `/pipelines/{pipeline_id}/nodes/{node_id}/selection` | Conditionally select a completed run using optimistic concurrency |

### 4.3 Artifact operations

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/artifacts` | List registered output artifacts |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/artifacts/{index}` | Download a retained file artifact |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/selected/artifacts/{artifact_name}` | Resolve a named artifact of the selected run |
| `GET` | `/pipelines/{pipeline_id}/nodes/{node_id}/selected/directories/{artifact_name}` | Resolve and verify a selected retained directory |
| `POST` | `/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/retain` | Queue output retention |

The node-oriented registration endpoints remain available for compatibility. New agent-oriented clients should generally use the simplified pipeline-level run-registration endpoint.

## 5. Create and inspect pipelines

### Create a pipeline

**Endpoint:**

```http
POST /caesar/api/v1.0/pipelines
```


Example request for a dataset-bound OXKAT pipeline:

```json
{
  "app": "oxkat",
  "dataset_id": "oxkat-test-dataset-v5",
  "name": "MeerKAT calibration experiments",
  "description": "Compare calibration and flagging configurations"
}
```

The supported creation fields are:

| Field | Required | Description |
| --- | --- | --- |
| `app` | Yes | Application enabled for Pipeline V2 |
| `dataset_id` | No | Accessible managed dataset associated with the pipeline |
| `name` | No | Human-readable pipeline name |
| `description` | No | Pipeline description |
| `metadata` | No | Optional application-independent metadata object |

A successful request returns HTTP `201` and the created pipeline record, including its generated `pipeline_id`, application identity, dataset association and initial selection state.

When `dataset_id` is supplied, CAESAR-REST validates its existence and the caller's access permissions before creating the pipeline.

The application configurator defines valid scientific stages and execution requirements. Dataset association does not automatically execute any scientific stage.

For dataset-bound pipelines, individual run-registration requests must not repeat `dataset_id`.

### List pipelines

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines
```

Returns pipelines visible to the authenticated owner.

### Retrieve pipeline metadata

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}
```

Returns the pipeline record, including its metadata and preferred-run selection state.

## 6. Register scientific experiments

**Endpoint:**

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs
```

The simplified V2 registration payload supports:

| Field | Purpose |
| --- | --- |
| `stage` | Required scientific stage |
| `node_id` | Optional logical experiment-group identifier |
| `parameters` | Optional application-specific scientific parameters |
| `inputs` | Optional named upstream artifact references |
| `input_artifacts` | Legacy-compatible alternative input representation |
| `idempotency_key` | Optional client-generated key for safe registration replay |
| `dataset_id` | Legacy-compatible field for pipelines without a dataset association; forbidden when the pipeline already has `dataset_id` |

The `inputs` and `input_artifacts` representations must not both be supplied in the same registration request.

For dataset-bound pipelines, the dataset association is resolved from the pipeline record and must not be supplied again in the run-registration request.

When `idempotency_key` is supplied, successful registration can be safely replayed using the same key and the same registration payload. Reusing a key with a different payload is rejected.

### 6.1 Initial run in a dataset-bound pipeline

For an OXKAT pipeline previously created with:

```json
{
  "app": "oxkat",
  "dataset_id": "oxkat-test-dataset-v5"
}
```

the initial GET_INFO run is registered using:

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs
```

Request body:

```json
{
  "stage": "GET_INFO"
}
```

The dataset association is inherited from the pipeline record. The application-specific stage input policy determines how the original Measurement Set is resolved and staged.

The run-registration request must not include `dataset_id` because the pipeline already specifies it.

The dataset must remain accessible to the authenticated caller and satisfy the scientific stage's input policy.

Successful registration returns HTTP `201` and creates a run in `PLANNED` state.

The response includes identifiers and registration metadata such as `run_id`, `node_id`, `run_name`, `sequence`, and resolved input information.

Registration does not submit a job. The registered run must subsequently be submitted explicitly through the Pipeline V2 submission endpoint.

### 6.2 Scientific parameters and OxKAT configuration

Scientific parameters are validated by the corresponding application configurator.

For OxKAT, stage-specific options may include an `oxkat_config` dictionary of validated scientific configuration overrides.

Conceptually, the registration request may include:

```json
{
  "stage": "1GC",
  "parameters": {
    "oxkat_config": {
      "OPTION_NAME": "OPTION_VALUE"
    }
  }
}
```

`OPTION_NAME` and `OPTION_VALUE` are illustrative placeholders, not actual OxKAT parameters. This fragment demonstrates the parameter structure, not a complete runnable experiment.

The server validates option names, value types and compatibility with the selected scientific stage.

Clients do not provide a separate arbitrary configuration-file path for these overrides. The application configurator translates validated scientific settings into the execution configuration used by the container.

Stage-specific required input artifacts and admissible scientific options remain subject to server-side validation.

## 7. Register downstream runs

Downstream runs consume named outputs of previously completed scientific stages.

Two supported reference styles are available.

### 7.1 Explicit upstream run references

A downstream experiment can reference a concrete upstream run ID and artifact name.

For example:

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

The referenced upstream run must belong to the same accessible pipeline and satisfy the required completion and artifact rules.

### 7.2 Selected upstream node references

A downstream experiment can instead reference the preferred run of a logical node:

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

The upstream `node_id` must identify an existing node within the pipeline. The example assumes a node explicitly named `flag`; the automatically generated ID for an omitted `node_id` would normally be `stage_flag`.

### 7.3 Named-input validation

Each named input must use one of these structures:

```json
{
  "run_id": "UPSTREAM_RUN_ID",
  "artifact": "ARTIFACT_NAME"
}
```

or:

```json
{
  "node_id": "UPSTREAM_NODE_ID",
  "selected": true,
  "artifact": "ARTIFACT_NAME"
}
```

No additional fields are accepted within either reference structure.

The `selected` value must be the JSON boolean `true`, not a string or numeric value.

Different named inputs in the same registration request may use different reference styles.

When selected-node references are supplied, the server reads a consistent selection snapshot, resolves the preferred runs and freezes their concrete upstream identities.

Input bindings include the source run and artifact index, together with associated integrity metadata.

Changing a selection later does not change those frozen references.

Registration is rejected when an upstream run is incomplete, a required selection is missing, an artifact is unavailable, or the referenced retained data does not satisfy the binding requirements.

## 8. Submit a registered run

**Endpoint:**

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}/submit
```

The endpoint expects an empty JSON object:

```json
{}
```

The server reconstructs the scientific execution request from the registered run.

Clients must not resubmit scientific parameters, artifact paths or storage locations.

The server validates the reserved run, stage policy, dataset binding, frozen input integrity and execution configuration before submitting the corresponding scheduler job.

A successful submission normally returns HTTP `200` with job submission information.

### One-shot submission

Pipeline V2 protects scheduler submission through atomic claims and durable one-shot submission intents.

A run is intended to be submitted only once.

If the HTTP request times out or the client loses its connection, the scheduler submission may nevertheless have occurred.

**Clients must not blindly repeat a submission request after an ambiguous outcome.**

Instead, retrieve the run record and inspect its status and submission information.

For full scheduler and retry considerations, see Section 13.

## 9. Inspect run status and readiness

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}
```

An illustrative response for a registered but not yet submitted run is:

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

This is a subset of the complete response.

### 9.1 Run lifecycle states

| State | Description |
| --- | --- |
| `PLANNED` | Experiment registered but not yet submitted |
| `SUBMITTING` | Submission has been claimed or initiated |
| `SUBMITTED` | Scheduler submission has been recorded |
| `SUBMISSION_FAILED` | Submission failed |
| `SUBMISSION_UNCERTAIN` | Submission outcome requires reconciliation |
| `RUNNING` | Scientific execution in progress |
| `COMPLETED` | Scientific execution completed successfully |
| `FAILED` | Scientific execution failed |
| `CANCELLED` | Scientific execution was cancelled |

These are pipeline-run states, distinct from the states used by the ordinary job-status API.

### 9.2 Artifact states

The `artifacts_status` field describes the outputs of the inspected run.

Possible values include:

| State | Description |
| --- | --- |
| `NOT_REGISTERED` | No registered output artifact set |
| `REGISTERED` | Outputs registered but not yet retained |
| `PENDING` | Retention pending |
| `COPYING` | Retention copy in progress |
| `FAILED` | Artifact-retention operation failed |
| `READY` | Retained artifact metadata indicates readiness |

These states do not describe already frozen upstream `input_artifacts`.

### 9.3 Readiness

The response exposes:

- `readiness.can_select`: whether the run is scientifically completed and eligible for preferred-run selection.
- `readiness.can_consume`: whether the registered output artifact set has retained metadata consistent with consumption readiness.

A run may have `can_select: true` and `can_consume: false`.

Readiness summaries do not replace authoritative artifact-integrity and input-eligibility checks during downstream registration.

### 9.4 Submission metadata

The `submission` object reports submission progress and recovery information.

Possible submission states include:

```text
NOT_STARTED
IN_PROGRESS
SUBMITTED
ACCEPTED
FAILED
UNCERTAIN
UNKNOWN
```

`ACCEPTED` means that scheduler submission was accepted; it does not mean that scientific execution succeeded.

`retry_allowed` is true only when the persisted lifecycle permits an initial submission attempt, normally for a `PLANNED` run.

It must not be interpreted as permission to retry an HTTP request whose outcome is unknown.

`requires_reconciliation` identifies submission conditions requiring investigation.

## 10. Inspect the pipeline tree and synchronize states

### Pipeline tree

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/tree
```

The tree summarizes logical nodes, registered runs, preferred selections, readiness and submission information.

Each node may report a `selected_run_id`.

The response may be relatively large because the implementation currently includes detailed input-binding metadata.

This endpoint is useful for scientific orchestration clients that need to inspect several alternative experiments and their dependencies.

### Synchronize pipeline state

**Endpoint:**

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/sync
```

This endpoint reconciles associated pipeline-run state with available persisted job records.

Clients should not confuse synchronization with a new scientific submission or an instruction to repeat scheduler execution.

For ambiguous submission outcomes, follow the reconciliation procedure and inspect the resulting run state before deciding on further action.

## 11. Preferred-run selection

A node maintains a mutable preferred-run pointer.

The selected run must belong to the specified node and must be scientifically `COMPLETED`.

Artifact retention is not required merely to select a completed run, although downstream consumption requires retained outputs.

### 11.1 Unconditional selection

**Endpoint:**

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/nodes/{node_id}/selection
```

Example:

```json
{
  "run_id": "NEW_PREFERRED_RUN_ID"
}
```

This operation replaces the previous preferred selection using last-writer-wins semantics.

It remains available for compatibility and intentional overrides.

### 11.2 Conditional selection

**Endpoint:**

```http
PUT /caesar/api/v1.0/pipelines/{pipeline_id}/nodes/{node_id}/selection
```

Example:

```json
{
  "run_id": "NEW_PREFERRED_RUN_ID",
  "expected_run_id": "CURRENT_PREFERRED_RUN_ID"
}
```

The server changes the selection only if the current selection matches `expected_run_id`.

To require that no run is currently selected, supply JSON `null`:

```json
{
  "run_id": "FIRST_PREFERRED_RUN_ID",
  "expected_run_id": null
}
```

If the expected selection does not match the current value, the server returns HTTP `409` without overwriting the selection.

Clients should retrieve the latest pipeline state, reevaluate their decision and then issue a new conditional request if appropriate.

**Conditional `PUT` selection is recommended for concurrent agents and multi-client orchestration.**

## 12. Artifact registration, retention and retrieval

Scientific pipeline outputs are registered as named artifacts.

Artifacts may represent ordinary files or directories containing scientific products.

The server manages their metadata, identities, retained storage and integrity information.

Clients should not construct internal filesystem paths from pipeline IDs, run IDs or artifact names.

### 12.1 List registered artifacts

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/artifacts
```

Returns the public artifact metadata for the specified owner-visible run.

### 12.2 Download a retained file artifact

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/artifacts/{index}
```

Downloads a registered and retained file artifact identified by its artifact index.

This endpoint is intended for file artifacts, not arbitrary directories.

### 12.3 Resolve a selected named file artifact

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/nodes/{node_id}/selected/artifacts/{artifact_name}
```

Resolves the named artifact associated with the currently preferred run.

The operation checks artifact availability according to the server's managed storage and access rules.

### 12.4 Resolve a selected directory artifact

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/nodes/{node_id}/selected/directories/{artifact_name}
```

Verifies a selected retained directory and returns its managed identity information without exposing internal filesystem paths.

Directory artifacts are not ordinary downloadable files.

For downstream scientific execution, use the managed artifact-binding mechanism rather than attempting to download and reconstruct directories through the REST client.

### 12.5 Request artifact retention

**Endpoint:**

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/nodes/{node_id}/runs/{run_id}/retain
```

This operation queues retention for an eligible completed run with registered outputs.

Retention copying is performed by the configured worker outside the HTTP request.

Clients can monitor the run's artifact status until it reaches `READY`, or investigate a failure if retention cannot complete.

Automatic registration and retention depend on deployment configuration.

### 12.6 Retention and downstream execution

Output retention is essential for multi-stage workflows.

Downstream runs bind specific upstream artifacts using managed, verified references. They do not rely on arbitrary paths inside the previous job's working directory.

Retained artifacts provide the stable storage needed for these cross-stage dependencies.

The scientific job directory and long-lived artifact-retention directory therefore serve different purposes.

See [Pipeline artifact retention deployment](../deployment/artifact-retention.md).

## 13. Submission safety and recovery

Pipeline V2 implements safeguards against duplicate scheduler submission.

Submission involves atomic run claiming and a durable submission intent recorded before contacting the scheduler.

The mechanism protects the run against ordinary repeated submission attempts, but it cannot make an unreliable network response equivalent to a definitive scheduler outcome.

### Uncertain submission

A connection timeout or HTTP failure during submission does not necessarily mean that Slurm rejected the job.

After an uncertain response, the client should:

1. Retrieve the run through `GET /pipelines/{pipeline_id}/runs/{run_id}`.
2. Inspect the run `status` and `submission` object.
3. Avoid automatically repeating `/submit`.
4. Use the established reconciliation procedure when the submission result remains uncertain.

Run states such as `SUBMITTING`, `SUBMITTED`, `SUBMISSION_FAILED` and `SUBMISSION_UNCERTAIN` must not be blindly resubmitted.

A stuck `SUBMITTING` run with or without a recorded intent may require investigation.

A new scientific attempt should normally be represented by a new run rather than resetting an already claimed one-shot submission.

### Distinguishing run and job identifiers

A pipeline run is not the same object as a scheduler job.

The run reservation receives a `run_id`.

Submission creates or associates the scheduler job and records a `job_id` in the submission metadata.

Clients should retain both identifiers and use the appropriate endpoints for pipeline lifecycle management and ordinary job execution monitoring.

## 14. Errors and validation

Pipeline endpoints return standard HTTP status codes together with endpoint-specific JSON responses.

| HTTP status | Typical meaning |
| --- | --- |
| `400` | Invalid request shape, identifiers, stage parameters or input fields |
| `401` / `403` | Authentication or authorization failure, depending on deployment |
| `404` | Requested owner-visible pipeline, run or artifact not found |
| `409` | Lifecycle conflict, missing selection, stale conditional update or unavailable upstream artifact |
| `503` | Service or configuration problem, or submission outcome requiring operational investigation |

The exact error code depends on the endpoint and validation failure.

Scientific configuration validation is performed by the server-side application configurator.

For example, OxKAT may reject a configuration override that is valid for one scientific stage but unsupported by another.

Missing upstream artifacts, inaccessible datasets and invalid cross-pipeline references are rejected rather than silently converted into arbitrary filesystem paths.

## 15. Compatibility with existing APIs

Scientific Pipeline V2 is additive to the established CAESAR-REST REST API.

The ordinary job endpoint remains available:

```http
POST /caesar/api/v1.0/job
```

It supports both the established V1 submission path and an explicit V2 submission path identified by `submission_version: 2`.

For agent-oriented workflows, the dedicated pipeline run-registration and submission endpoints are preferred because they preserve the registered experiment contract and frozen input dependencies.

The node-oriented run-registration API is also retained for compatibility.

Existing interfaces should not be interpreted as bypasses for dataset authorization, managed input paths or artifact-integrity enforcement.

## 16. Client orchestration recommendations

An external scientific orchestration client such as MAASAI should:

1. Discover the supported application and its scientific input/output contract.
2. Create or retrieve a dataset-bound pipeline.
3. Verify dataset inspection and scientific target discovery when required.
4. Register and submit the initial dataset-level processing stages.
5. Monitor completion, artifact registration and retention.
6. Evaluate completed experiments and conditionally select preferred runs.
7. Query scientific readiness and bulk-plan eligible downstream targets.
8. Bulk-register unchanged planning proposals using stable idempotency keys.
9. Submit each registered run individually according to the client's scheduling and concurrency policy.
10. Handle target-specific execution, retention and registration failures independently.
11. Download and examine available diagnostic products when evaluating scientific quality.
12. Register alternative experiments with new idempotency keys when scientific parameters need adjustment.
13. Select preferred completed experiments and refresh readiness before planning downstream stages.
14. Continue until the scientific workflow is complete.

MAASAI is responsible for scientific strategy, evaluation criteria, experiment comparison, scheduling decisions and stage progression.

CAESAR-REST validates, submits and monitors individual runs, manages artifacts, enforces authorization and preserves immutable provenance.

The generic pipeline infrastructure does not automatically evaluate scientific quality or advance to downstream stages.

See the [MAASAI orchestration contract](../maasai_orchestration_contract.md) for API sequencing, partial failures, idempotency and recovery rules.

## 17. Scientific readiness and target discovery

Scientific readiness provides application-specific information about whether discovered scientific targets can proceed to particular pipeline stages.

It complements generic pipeline readiness, which reports the state of selected runs and registered artifacts.

### 17.1 Generic pipeline readiness

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/readiness
```

Returns a metadata-based snapshot of the pipeline's selected runs and their readiness.

The response supports determining whether selected upstream outputs are completed and available for subsequent processing.

Generic readiness does not perform scientific target evaluation and does not reserve inputs for future execution.

### 17.2 Scientific readiness

**Endpoint:**

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/scientific-readiness
```

The response uses schema `caesar.pipeline-scientific-readiness.v1`.

Its top-level fields include:

| Field | Description |
| --- | --- |
| `schema` | Response schema identifier |
| `pipeline_id` | Inspected pipeline |
| `dataset_id` | Pipeline-associated managed dataset |
| `application` | Pipeline application |
| `scientific` | Application-specific readiness result |

Scientific readiness requires a dataset-bound pipeline and an application configurator implementing a scientific readiness provider.

The provider receives authorized dataset metadata and persisted pipeline runs. It evaluates scientific prerequisites using the current inspection metadata, selected upstream runs and retained-artifact readiness.

No scheduler job is submitted, no run is registered and no dataset inspection is initiated by this endpoint.

### 17.3 OXKAT target readiness

For OXKAT, scientific readiness uses dataset inspection metadata to identify science targets and their field IDs.

The `scientific` object includes:

| Field | Description |
| --- | --- |
| `provider` | Scientific readiness provider (`oxkat`) |
| `status` | Overall scientific readiness status |
| `inspection_status` | Dataset inspection status |
| `target_count` | Number of discovered targets, when ready |
| `targets` | Target-specific readiness records |

A target record includes `field_id`, `name` and `next_steps`.

The `next_steps` mapping contains readiness information for FLAG and 2GC, including whether an eligible upstream input combination exists, associated blocking reasons and candidate artifact references.

Important overall statuses include:

- `READY`: target discovery is available and complete.
- `INSPECTION_NOT_READY`: the required inspection result is not ready.
- `INSPECTION_INCOMPLETE`: inspection metadata is insufficient for reliable target planning.

A `READY` overall status does not imply that every individual target can proceed to every stage.

For example, `NO_CONSUMABLE_1GC_TARGET_INPUTS` indicates that a target has no eligible selected and consumable 1GC inputs for FLAG.

Similarly, `NO_CONSUMABLE_FLAG_TARGET_INPUTS` indicates that no eligible FLAG inputs are available for 2GC.

Scientific readiness may also report `AMBIGUOUS_UPSTREAM_INPUTS` when multiple eligible candidates prevent unambiguous input selection.

### 17.4 Readiness is advisory

Scientific readiness and generic readiness are read-only snapshots.

They do not guarantee that the same inputs will remain eligible when a later registration request is processed.

The authoritative registration and artifact-binding layers revalidate upstream references, authorization and input integrity.

Clients should refresh readiness after relevant changes to upstream run state, retention or preferred-run selection.


## 18. Bulk planning and registration

Pipeline V2 supports read-only bulk planning and controlled bulk registration for application providers that implement target-specific scientific readiness.

These operations allow an external orchestration client to manage multiple scientific targets without introducing automatic pipeline execution.

### 18.1 Bulk planning

**Endpoint:**

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/bulk-plan
```

Example request:

```json
{
  "stage": "FLAG",
  "targets": ["MAXIJ1348", "GX_339-4"]
}
```

The request supports:

| Field | Required | Description |
| --- | --- | --- |
| `stage` | Yes | Scientific stage to plan |
| `targets` | No | Optional nonempty list of target identities |

When `targets` is omitted, the application provider plans all discovered science targets supported by the requested stage.

The generic request validator accepts up to 128 distinct target identities. Empty lists, duplicate targets, unsupported fields and invalid stage values are rejected.

The current OXKAT provider supports bulk planning for FLAG and 2GC.

The response uses schema `caesar.pipeline-bulk-plan.v1` and includes:

| Field | Description |
| --- | --- |
| `schema` | Response schema identifier |
| `pipeline_id` | Pipeline identifier |
| `dataset_id` | Associated dataset |
| `application` | Application name |
| `stage` | Requested scientific stage |
| `status` | Overall planning status |
| `summary` | Counts of total, plannable and blocked items |
| `items` | Target-specific planning results |

Each OXKAT item contains:

| Field | Description |
| --- | --- |
| `field_id` | Inspected scientific field identifier |
| `target` | Scientific target name |
| `can_register` | Whether a registration proposal is available |
| `blocking_reasons` | Reasons preventing registration |
| `registration` | Proposed run-registration object, or null |

A successful planning operation can return blocked targets. A top-level status of `READY` means the planner produced a valid result, not that every target can be registered.

An eligible proposal includes `stage`, `node_id`, `parameters` and explicit `inputs` referencing the selected upstream runs and their registered artifact indices.

For OXKAT, target-specific node identifiers use the pattern:

```text
stage_flag_f<field_id>
stage_2gc_f<field_id>
```

Bulk planning is strictly read-only. It does not create pipeline runs, reserve artifacts, change selections or submit scheduler jobs.

### 18.2 Controlled bulk registration

**Endpoint:**

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/bulk-register
```

Example request envelope:

```json
{
  "items": [
    {
      "idempotency_key": "maasai:flag:f1:attempt1",
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

The registration object and artifact indices above are illustrative. In real requests, clients must copy the complete, unchanged `registration` object returned by the current bulk planner.

Bulk registration accepts between 1 and 32 items per request.

Each item must contain exactly:

- `idempotency_key`
- `registration`

The request must not contain duplicate idempotency keys or duplicate `(stage, target)` identities.

For a first-time registration, CAESAR-REST recomputes scientific readiness and verifies that the submitted registration exactly matches the current planning proposal.

Modified or stale proposals are rejected.

### 18.3 Bulk registration response

A valid bulk registration envelope returns HTTP `200` with schema `caesar.pipeline-bulk-registration.v1`.

The response includes a `summary` containing:

- `total`
- `created`
- `replayed`
- `failed`

Each result item has one of three statuses:

| Status | Meaning |
| --- | --- |
| `CREATED` | A new pipeline run was registered |
| `REPLAYED` | The same idempotent registration already exists |
| `FAILED` | Registration failed for this item |

Successful items include the idempotency key, run ID, node ID and current run status.

Failed items include the idempotency key, HTTP-equivalent error status and error description.

Bulk registration is not an all-or-nothing transaction.

A request can return HTTP `200` while individual items have failed. Clients must inspect `summary.failed` and every item status.

Successful registrations remain persisted even when other items fail.

### 18.4 Registration idempotency

Each registration key is scoped to the authenticated owner and pipeline.

Keys contain 1-128 ASCII characters, begin with an alphanumeric character, and otherwise permit letters, digits, underscores, dots, colons and hyphens.

Clients must persist the original registration payload and its idempotency key before sending the request.

After an uncertain HTTP response, repeat the same registration with the same key and unchanged payload.

A matching registration returns `REPLAYED` with the existing run identity. Its current execution status may no longer be `PLANNED`.

Reusing an idempotency key with a different registration payload produces a conflict.

When scientific parameters or input references are intentionally changed, register a new experiment using a new idempotency key.

Registration idempotency does not authorize repeated submission of a scheduler job.

### 18.5 Scientific alternatives and run submission

Bulk planning produces default proposals from the application-specific scientific readiness provider.

Bulk registration requires these proposals to remain unchanged.

To register a different scientific parameter configuration, clients should use the individual endpoint:

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs
```

For OXKAT, scientific alternatives may specify validated `oxkat_config` overrides and appropriate target-specific inputs.

Alternative experiments can share a logical node so that one preferred run can subsequently be selected.

Bulk registration does not launch jobs.

Each registered run must be submitted explicitly:

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}/submit
```

The request body is an empty JSON object.

The client determines concurrency, scheduling order, retries as new experiments, scientific evaluation and preferred-run selection.

CAESAR-REST remains responsible for run validation, submission safety, execution monitoring, artifact retention and immutable input binding.

### 18.6 Partial failures and downstream progression

Different scientific targets are independent.

Failure to register, execute or retain one target does not imply failure of unrelated target branches.

The orchestrating client should track each target's field ID, stage, node ID, run ID, registration key, blocking reasons and execution state.

After a completed run has produced suitable retained artifacts, the client may evaluate it and select it through the conditional selection endpoint.

The client should then refresh scientific readiness and bulk planning for the next stage.

For OXKAT, FLAG proposals consume eligible selected 1GC products. The 2GC planner requires the corresponding eligible FLAG products, including the target Measurement Set, project metadata and FLAG image artifact.

Downstream registrations freeze concrete upstream run and artifact identities. Later changes to preferred-run selections do not change those immutable bindings.

For the complete MAASAI orchestration workflow, see [MAASAI orchestration contract](../maasai_orchestration_contract.md).

## References

- [REST API overview](overview.md)
- [Data and datasets API](data.md)
- [Application discovery](applications.md)
- [Jobs REST API](jobs.md)
- [Slurm deployment](../deployment/slurm.md)
- [Job monitoring](../deployment/job-monitoring.md)
- [Pipeline artifact retention](../deployment/artifact-retention.md)
- [MAASAI integration guide](../maasai_integration.md)
- [MAASAI Pipeline V2 orchestration contract](../maasai_orchestration_contract.md)
- [Future developments and integrations](../future-developments.md)
- [Archived original README](../archive/ORIGINAL_README.md)
