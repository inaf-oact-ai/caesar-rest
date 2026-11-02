# Jobs REST API

CAESAR-REST provides REST endpoints for submitting scientific jobs, listing submitted jobs, retrieving execution status, downloading results and cancelling running jobs.

All endpoints use the base path `/caesar/api/v1.0`. When authentication is enabled, protected requests require a valid OAuth 2.0 bearer access token.

See [REST API overview](overview.md) and [Application discovery](applications.md).

## 1. Job execution model

A scientific job is submitted asynchronously to the execution backend configured for the CAESAR-REST deployment.

The supported backend integrations include Slurm, Kubernetes and the legacy Celery backend. Slurm is the recommended backend for current deployments.

Submission returns a job identifier that clients can use to query execution status, retrieve available outputs or request cancellation.

A successfully accepted submission does not mean that the scientific application has completed successfully.

Job status information is persisted in MongoDB and updated by the corresponding execution and monitoring infrastructure.

### Job ownership

Jobs are registered in user-specific MongoDB collections.

Job listing, status retrieval, output retrieval and cancellation use the current caller's storage identity to locate the corresponding job records.

A job identifier belonging to another user does not grant access to that user's job.

## 2. Submit a scientific job

**Endpoint:**

```http
POST /caesar/api/v1.0/job
```

The endpoint accepts a JSON object describing the scientific application, its input data and its execution options.

### Standard job submission (V1)

An illustrative request for the `caesar` source-finding application is:

```bash
curl --fail-with-body -X POST \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{
		"app": "caesar",
		"data_inputs": {
			"data": "39ca08fc5c7c446d8756a48088ee684c"
		},
		"job_options": {
			"run": true,
			"no-logredir": true,
			"no-mpi": true,
			"no-nestedsearch": true,
			"no-extendedsearch": true
		}
	}' \
	"https://server.example.org:8444/caesar/api/v1.0/job"
```

The request contains:

| Field | Purpose |
| --- | --- |
| `app` | Scientific application identifier |
| `data_inputs` | Input data specification |
| `job_options` | Application-specific execution options |
| `tag` | Optional user-defined job tag |
| `submission_version` | Optional submission contract version |

When `submission_version` is omitted, the endpoint uses the established V1 submission path.

Scientific application options must be compatible with the registered application configurator. Clients can inspect available options using:

```http
GET /caesar/api/v1.0/app/{app_name}/describe
```

The example above illustrates the historical uploaded-file UUID input convention. The appropriate `data_inputs` structure depends on the selected input format, application and deployment configuration.

For managed datasets, clients should use accessible dataset IDs rather than direct filesystem paths within managed dataset roots.

See [Data and datasets API](data.md).

### Submission response

A successful V1 submission returns a JSON object containing the generated job ID and submission metadata.

An illustrative response is:

```json
{
  "app": "caesar",
  "data_inputs": "39ca08fc5c7c446d8756a48088ee684c",
  "job_id": "a4095b815a074d81a0cc447762aa29f1",
  "job_options": {
    "no-extendedsearch": true,
    "no-logredir": true,
    "no-mpi": true,
    "no-nestedsearch": true,
    "run": true
  },
  "state": "PENDING",
  "status": "Job submitted and registered with success",
  "submit_date": "2024-12-19T10:00:42.865802",
  "tag": ""
}
```

The timestamps and identifiers are illustrative.

The returned `job_id` identifies the scheduler-submitted job within CAESAR-REST.

A `PENDING` state indicates that execution has not yet been reported as completed.

### Validation and submission failures

The endpoint validates the submitted application, input data and scientific options before attempting execution.

Invalid requests may be rejected with HTTP `400`. Scheduler, execution-preparation or persistence failures may result in server errors.

Some failed submissions include:

```json
{
  "app": "caesar",
  "job_id": "",
  "state": "ABORTED",
  "status": "Invalid request data!",
  "submit_date": ""
}
```

The precise error message depends on the validation or execution failure.

Clients should check the HTTP response status and returned JSON instead of assuming that every response contains a usable job ID.

## 3. Pipeline V2 job submission

The `/job` endpoint also supports an explicit Pipeline V2 submission contract selected by:

```json
{
  "submission_version": 2
}
```

In that mode, the request is processed by the Pipeline V2 submission adapter rather than the ordinary V1 input-processing path.

Pipeline V2 associates scientific execution with registered pipelines and reserved runs. It enforces additional validation of ownership, stage parameters, dataset access and upstream artifact bindings.

The recommended agent-oriented workflow uses the dedicated Pipeline V2 endpoints to create and reserve runs and then submit them.

In particular:

```http
POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}/submit
```

submits an already reserved V2 run according to the dedicated Pipeline V2 contract.

**Do not confuse `job_id` with `run_id`.** A run reservation represents a registered scientific experiment, while the scheduler job is created during submission.

The complete request contracts, run lifecycle and artifact-binding rules are documented in the [Scientific Pipeline V2 detailed API reference](../pipeline_v2_api.md).

## 4. List submitted jobs

**Endpoint:**

```http
GET /caesar/api/v1.0/jobs
```

Example:

```bash
curl --fail-with-body \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	"https://server.example.org:8444/caesar/api/v1.0/jobs"
```

The endpoint returns a JSON array of job records associated with the caller's storage identity.

Unlike the historical heading "Get job IDs", the current response includes stored job metadata rather than only an array of identifiers.

Records may contain fields such as:

- `job_id`, `app` and `submit_date`.
- `state`, `status` and scheduler identification.
- `job_options`, `data_inputs` and `tag`.
- `pid`, `elapsed_time` and `exit_code`.
- Pipeline identifiers and execution metadata for pipeline-associated jobs.

The exact fields depend on the job's execution mode and the metadata available in MongoDB.

## 5. Retrieve job status

**Endpoint:**

```http
GET /caesar/api/v1.0/job/{job_id}/status
```

Example:

```bash
curl --fail-with-body \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	"https://server.example.org:8444/caesar/api/v1.0/job/a4095b815a074d81a0cc447762aa29f1/status"
```

An illustrative response is:

```json
{
  "job_id": "a4095b815a074d81a0cc447762aa29f1",
  "pid": "11539",
  "state": "SUCCESS",
  "status": "Process terminated with success",
  "exit_code": 0,
  "elapsed_time": "27.3435878754",
  "tag": ""
}
```

The current implementation uses `exit_code`, not the historical `exit_status` field.

The `pid` field contains an execution-backend identifier and should not universally be interpreted as a local operating-system process ID. Its meaning depends on the configured scheduler.

The `elapsed_time` representation also follows the stored job record and should not be assumed to be a numeric JSON value in every response.

### Job execution states

Job states encountered by clients include:

| State | Meaning |
| --- | --- |
| `PENDING` | Job submitted or awaiting execution |
| `STARTED` | Execution started |
| `RUNNING` | Job execution in progress |
| `SUCCESS` | Job completed successfully |
| `FAILURE` | Job execution failed |
| `ABORTED` | Job execution or submission aborted |
| `TIMED-OUT` | Job exceeded an execution time limit |
| `CANCELED` | Job cancelled by the user |

The precise state transitions depend on the execution backend and monitoring implementation.

Clients should treat the returned state as authoritative and should not rely exclusively on HTTP success codes to determine scientific execution outcomes.

A job that does not exist in the caller's collection results in HTTP `404`.

## 6. Download job outputs

**Endpoint:**

```http
GET /caesar/api/v1.0/job/{job_id}/output
```

Example:

```bash
curl --fail-with-body \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	-o job_output.tar.gz \
	"https://server.example.org:8444/caesar/api/v1.0/job/a4095b815a074d81a0cc447762aa29f1/output"
```

The endpoint attempts to return the stored job output archive as a downloadable file.

For the historical execution layout, this is the archive:

```text
job_{job_id}.tar.gz
```

located in the corresponding job working directory.

The archive may contain execution logs, run scripts, scientific results and other files generated by the application, depending on the job and its execution environment.

### Output availability

The endpoint checks job ownership and recorded execution state.

For jobs in `PENDING`, `STARTED`, `RUNNING` or `ABORTED`, the current implementation returns HTTP `202` with a JSON message indicating that output is not available.

For other states, it attempts to locate the requested archive.

A missing archive may result in a server error even if the job has reached a terminal state.

Therefore, job completion does not guarantee that a downloadable archive exists.

### Pipeline V2 outputs

Pipeline V2 retained artifacts are managed separately from the historical job output archive.

For pipelines, clients should use the corresponding artifact registration, retention and retrieval endpoints rather than assuming that `/job/{job_id}/output` represents the complete retained scientific output set.

See [Pipeline artifact retention](../deployment/artifact-retention.md) and [Scientific Pipeline V2 API reference](../pipeline_v2_api.md).

## 7. Retrieve application-specific outputs

CAESAR-REST retains additional job output endpoints, particularly for scientific applications producing source catalogs and image previews.

| Method | Endpoint | Content |
| --- | --- | --- |
| `GET` | `/job/{job_id}/sources` | Source catalog as JSON |
| `GET` | `/job/{job_id}/output-sources` | Source catalog file |
| `GET` | `/job/{job_id}/source-components` | Component catalog as JSON |
| `GET` | `/job/{job_id}/output-components` | Component catalog file |
| `GET` | `/job/{job_id}/preview` | Preview image encoded in a JSON response |
| `GET` | `/job/{job_id}/output-plot` | Preview image file |

All paths in the table are relative to `/caesar/api/v1.0`.

These endpoints are application-specific conveniences. They depend on the presence of files matching the naming patterns expected by the current implementation.

They should not be treated as a generic artifact retrieval API for arbitrary scientific applications.

## 8. Cancel a job

**Endpoint:**

```http
POST /caesar/api/v1.0/job/{job_id}/cancel
```

Example:

```bash
curl --fail-with-body -X POST \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	"https://server.example.org:8444/caesar/api/v1.0/job/a4095b815a074d81a0cc447762aa29f1/cancel"
```

The endpoint checks the caller's ownership of the job and requests cancellation through the configured execution backend.

For a successful cancellation, the service updates the stored job state to `CANCELED` and returns a confirmation message.

For example:

```json
{
  "status": "Job canceled and status updated in DB"
}
```

The existing route also accepts `GET` for historical compatibility. New clients should use `POST` because cancellation changes server-side execution state.

A job already in `SUCCESS`, `FAILURE` or `TIMED-OUT` is treated as already completed and is not cancelled.

Cancellation may fail if the scheduler rejects the request or if the job's execution state has already changed.

The caller should subsequently retrieve job status to confirm the final recorded state.

## 9. Client integration recommendations

Clients should:

- Retrieve available applications and options before constructing job requests.
- Use authenticated identities consistently for submission, monitoring and output retrieval.
- Validate request payloads locally where possible, while treating server-side validation as authoritative.
- Store the returned job ID for subsequent status, cancellation and output requests.
- Handle asynchronous execution by querying job state rather than assuming immediate completion.
- Distinguish job execution state from Pipeline V2 artifact readiness.
- Use the dedicated Pipeline V2 contract for stage-based workflows and retained scientific outputs.

## References

- [REST API overview](overview.md)
- [Application discovery](applications.md)
- [Data and datasets API](data.md)
- [Scientific Pipeline V2 concepts and examples](scientific-pipelines.md)
- [Scientific Pipeline V2 detailed API reference](../pipeline_v2_api.md)
- [Job monitoring deployment](../deployment/job-monitoring.md)
- [Pipeline artifact retention](../deployment/artifact-retention.md)
- [Archived original README](../archive/ORIGINAL_README.md)
