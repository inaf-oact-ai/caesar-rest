# Scientific Pipeline V2 API

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 1164–1457). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

## Scientific Pipeline V2 API

CAESAR-REST provides an authenticated API for registering,
executing and monitoring multi-stage scientific pipelines.

The pipeline API is application-independent. Scientific stages,
allowed parameters and input mappings are configured on the
server. The examples below use OXKAT, but the same pipeline
infrastructure can support other scientific applications.

All endpoints use the prefix:

`/caesar/api/v1.0`

Pipeline requests require authentication. REST clients should
provide a valid access token:

`Authorization: Bearer <access-token>`

Refer to the Keycloak/OpenID Connect section above for
authentication and TLS configuration.

### Pipeline concepts

A **pipeline** groups related scientific experiments.

A **stage** identifies the scientific processing operation
(e.g. GET_INFO, 1GC, FLAG or 2GC for OXKAT).

A **node** groups alternative runs for the same stage.
Different nodes may represent independent experimental groups
for the same scientific stage. For example, an agent may use
`flag_conservative` and `flag_aggressive` as separate nodes
for the OXKAT `FLAG` stage.

Each node maintains its own preferred-run selection.

If `node_id` is omitted, CAESAR-REST assigns a generic
identifier such as `stage_flag` or `stage_2gc`.

A **run** represents a registered experiment with fixed
scientific parameters and input dependencies.

A **selected run** is the preferred completed experiment
within a node. Selection is mutable, but previously registered
downstream input bindings remain immutable.

### Core REST endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/pipelines` | Create a pipeline |
| GET | `/pipelines` | List pipelines |
| GET | `/pipelines/{pipeline_id}` | Retrieve pipeline metadata |
| GET | `/pipelines/{pipeline_id}/runs` | List pipeline runs |
| POST | `/pipelines/{pipeline_id}/runs` | Register a V2 run |
| GET | `/pipelines/{pipeline_id}/runs/{run_id}` | Retrieve run details and readiness |
| POST | `/pipelines/{pipeline_id}/runs/{run_id}/submit` | Submit a registered run |
| GET | `/pipelines/{pipeline_id}/tree` | Retrieve pipeline execution tree |
| POST | `/pipelines/{pipeline_id}/sync` | Synchronize run states |
| POST | `/pipelines/{pipeline_id}/nodes/{node_id}/selection` | Select a completed run unconditionally |
| PUT | `/pipelines/{pipeline_id}/nodes/{node_id}/selection` | Conditionally select a completed run |

Additional node-oriented run, artifact listing, artifact download,
selected-artifact resolution and retention endpoints are documented
in the [Pipeline V2 API reference](docs/pipeline_v2_api.md).

### Quick start

#### 1. Create a pipeline

`POST /caesar/api/v1.0/pipelines`

```json
{
  "app": "oxkat",
  "name": "OXKAT calibration experiments",
  "description": "Agent-driven calibration and imaging"
}
```

The response contains a `pipeline_id`.

#### 2. Register an initial run

`POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs`

```json
{
  "stage": "GET_INFO",
  "dataset_id": "oxkat-test-dataset-v3"
}
```

This creates a `PLANNED` run; it does not submit a job.

#### 3. Submit the registered run

`POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}/submit`

```json
{}
```

CAESAR-REST derives the execution request from the registered
run. Clients do not resubmit scientific parameters or storage paths.

#### 4. Monitor the run

`GET /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}`

The response includes:

```json
{
  "status": "COMPLETED",
  "artifacts_status": "READY",
  "readiness": {
    "can_select": true,
    "can_consume": true
  },
  "submission": {
    "state": "ACCEPTED",
    "retry_allowed": false,
    "requires_reconciliation": false
  }
}
```

These values illustrate a successfully completed and retained run.

`COMPLETED` describes scientific execution. `READY` indicates
that the registered outputs have complete retained-artifact
metadata. Actual downstream input binding still verifies artifact
availability and integrity.

The submission state `ACCEPTED` does not by itself mean that
the scientific execution succeeded.

#### 5. Register a downstream run with named inputs

A typical OXKAT calibration pipeline progresses through:

`GET_INFO → 1GC → FLAG → 2GC`

Each stage produces registered scientific artifacts that can be
consumed by subsequent stages. The orchestrating application
decides whether to execute another experiment, select a preferred
run or proceed to the next scientific stage.

The examples below focus on 2GC input registration. See the
MAASAI integration guide for the complete orchestration workflow.

A later OXKAT stage can reference concrete artifacts from
an upstream run:

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

Alternatively, the client can reference the currently selected
run of a logical node:

```json
{
  "stage": "2GC",
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

The selected run is resolved at registration time. The server
stores immutable upstream run IDs, artifact indices and integrity
metadata. Later changes to a preferred selection do not affect
previously registered downstream runs.

The node identifier must match an existing node in the pipeline.

### Preferred-run selection

To select a completed run unconditionally:

`POST /pipelines/{pipeline_id}/nodes/{node_id}/selection`

```json
{
  "run_id": "PREFERRED_RUN_ID"
}
```

For concurrency-safe updates, use PUT:

`PUT /pipelines/{pipeline_id}/nodes/{node_id}/selection`

```json
{
  "run_id": "NEW_PREFERRED_RUN_ID",
  "expected_run_id": "CURRENT_PREFERRED_RUN_ID"
}
```

The operation succeeds only if the current selection matches
`expected_run_id`. Otherwise the server returns HTTP 409.

Set `expected_run_id` to JSON `null` when the node is expected
to have no selected run.

Conditional selection is recommended for concurrent agents.

### Submission safety

Pipeline V2 uses atomic run claims and durable one-shot
submission intents to prevent duplicate scheduler submissions.

A timed-out HTTP request does not necessarily mean that Slurm
rejected the submission.

Clients should retrieve the run status and inspect the
`submission` object before taking further action.

For uncertain submissions, automatic resubmission is not safe.
Reconciliation may be required. 

The `submission.retry_allowed` field indicates whether the
stored run state permits an initial submission attempt.

When `retry_allowed` is `true` for a `PLANNED` run, the server
still performs atomic claiming and all normal submission checks.

This field must not be interpreted as authorization to
automatically retry a timed-out HTTP submission request.

Runs in `SUBMITTING`, `SUBMITTED`, `SUBMISSION_FAILED` or
`SUBMISSION_UNCERTAIN` must not be blindly resubmitted.

### Artifact lifecycle

Scientific completion, artifact registration, retention and
preferred-run selection are separate operations.

A completed run may be selected before its outputs are retained,
but downstream stages require retained and verified input artifacts.

CAESAR-REST maintains frozen artifact identities and integrity
metadata so that downstream runs consume the intended outputs
even when preferred selections change.

### Detailed documentation

- [Pipeline V2 API reference](docs/pipeline_v2_api.md)
- [MAASAI integration guide](docs/maasai_integration.md)

The API reference documents the complete route set, artifact
operations, run lifecycle, validation rules and error handling.

The MAASAI guide explains agent-oriented registration, submission,
monitoring, experiment comparison, selected-run resolution and
safe recovery from ambiguous submission outcomes.

---



