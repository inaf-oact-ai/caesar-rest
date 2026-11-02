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
| **Pipeline** | Owner-scoped collection of scientific experiments and execution history |
| **Stage** | Scientific processing operation validated by the application |
| **Node** | Logical group of alternative runs, normally associated with a stage |
| **Run** | Registered experiment with fixed scientific parameters and input dependencies |
| **Selection** | Mutable pointer identifying the preferred completed run of a node |
| **Artifact** | Registered scientific output file or directory |
| **Artifact binding** | Immutable downstream reference to an upstream artifact |
| **Retention** | Copying and verification of outputs in managed long-lived artifact storage |
| **Submission intent** | Durable record used to protect a run against duplicate scheduler submission |

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

A typical workflow is:

1. Create a pipeline.
2. Register an initial run, possibly bound to a managed dataset.
3. Submit the registered run.
4. Monitor execution until scientific completion.
5. Register and retain its output artifacts.
6. Optionally select the preferred completed run.
7. Register downstream runs with validated upstream artifact references.
8. Repeat for subsequent scientific stages.

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

Example request:

```json
{
  "app": "oxkat",
  "name": "MeerKAT calibration experiments",
  "description": "Compare alternative calibration and flagging configurations"
}
```

The response includes a server-generated `pipeline_id`.

The application identity is associated with the pipeline. Application configurators determine the valid stages and scientific execution requirements.

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
| `node_id` | Optional logical node identifier |
| `parameters` | Optional stage-specific scientific parameters |
| `dataset_id` | Optional managed dataset input, subject to stage policy |
| `inputs` | Optional named upstream artifact references |
| `input_artifacts` | Legacy-compatible alternative input representation |

The `inputs` and `input_artifacts` representations must not both be supplied in one registration request.

### 6.1 Initial dataset-bound run

An initial OxKAT run may use a managed dataset:

```json
{
  "stage": "GET_INFO",
  "dataset_id": "oxkat-test-dataset-v3"
}
```

The dataset must exist, be accessible to the caller and satisfy the scientific stage's input policy.

Successful registration returns HTTP `201` and creates a run in `PLANNED` state.

The response includes identifiers and registration metadata such as `run_id`, `node_id`, `run_name`, `sequence`, and resolved input information.

Registration does not submit a job.

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

An external scientific agent should:

1. Create or retrieve its pipeline.
2. Register immutable experiments with validated scientific parameters.
3. Submit each registered run only once.
4. Monitor the scientific lifecycle and inspect submission uncertainty.
5. Wait for required artifact registration and retention.
6. Compare completed experiments using application-specific scientific criteria.
7. Update preferred selections using conditional `PUT` requests.
8. Register downstream experiments using explicit or selected upstream artifact references.
9. Continue until the required scientific workflow is complete.

CAESAR-REST validates, schedules, monitors and manages pipeline resources. It does not independently decide which scientific experiment is preferable.

That decision belongs to the orchestrating application or scientific user.

For an example of external agent orchestration, see the [MAASAI integration guide](../maasai_integration.md).

## References

- [REST API overview](overview.md)
- [Data and datasets API](data.md)
- [Application discovery](applications.md)
- [Jobs REST API](jobs.md)
- [Slurm deployment](../deployment/slurm.md)
- [Job monitoring](../deployment/job-monitoring.md)
- [Pipeline artifact retention](../deployment/artifact-retention.md)
- [MAASAI integration guide](../maasai_integration.md)
- [Archived original README](../archive/ORIGINAL_README.md)
