# Data and datasets REST API

CAESAR-REST provides endpoints for uploading, listing, downloading and deleting user files; registering and managing scientific datasets; and asynchronously inspecting registered datasets to discover scientific metadata and processing targets.

Dataset inspection is independent of scientific pipeline execution. Inspection metadata can be consumed by application-specific scientific readiness providers and target-aware pipeline planning without requiring the orchestrating client to access the underlying dataset filesystem.

All endpoints use the base path `/caesar/api/v1.0`. When authentication is enabled, protected requests require a valid OAuth 2.0 bearer access token.

See [REST API overview](overview.md) and [Keycloak authentication](../deployment/authentication.md).

## 1. Data and dataset concepts

CAESAR-REST distinguishes between two types of data resources:

- **Uploaded files:** Files uploaded by an API client, stored in the caller's user-specific data directory and referenced through generated file UUIDs.
- **Managed datasets:** Scientific datasets registered with a dataset ID, metadata, a filesystem location and access-control settings.

Uploaded files and managed datasets have separate registration mechanisms and APIs.

A file UUID identifies an uploaded file belonging to the caller's storage identity. A managed dataset ID identifies a registered scientific dataset accessible according to the registry's authorization rules.

Uploaded files are registered in user-specific MongoDB collections and stored in user-specific filesystem directories. Listing, downloading and deleting uploaded files operate within the current caller's storage identity. These uploaded-file operations are distinct from the managed dataset registry and its team-based access rules.

For managed datasets, clients should use dataset IDs rather than supplying arbitrary filesystem paths.

## 2. Upload files

**Endpoint:**

```http
POST /caesar/api/v1.0/upload
```

The endpoint accepts a `multipart/form-data` request containing a file field named `file`.

An optional form field named `tag` can associate a descriptive tag with the uploaded file.

Example:

```bash
curl --fail-with-body -X POST \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	-F "file=@VGPS_cont_MOS017.fits" \
	-F "tag=radio-image" \
	"https://server.example.org:8444/caesar/api/v1.0/upload"
```

Do not manually set the multipart `Content-Type` header when using `curl -F`; curl generates the correct boundary automatically.

The server validates the file extension against the configured `UPLOAD_ALLOWED_FILE_FORMATS`, stores the file in the caller's data directory and registers its metadata in the corresponding MongoDB file collection.

A successful response has the following structure (illustrative values; timestamps and UUIDs vary for each upload):

```json
{
  "date": "2020-04-24T17:04:26.174333",
  "filename_orig": "VGPS_cont_MOS017.fits",
  "format": "fits",
  "size": 4.00726318359375,
  "tag": "radio-image",
  "status": "File uploaded with success",
  "uuid": "250fdf5ed6a044888cf4406338f9e73b"
}
```

The `size` field is expressed in MiB. The `uuid` identifies the uploaded file for subsequent API operations.

The response no longer exposes the server-side storage path.

Uploads can fail with HTTP `400` for missing file data, `415` for unsupported file types, or a server error when storage or metadata registration fails.

The allowed file formats depend on server configuration. Clients should not assume every scientific file format is accepted.

## 3. List uploaded files

**Endpoint:**

```http
GET /caesar/api/v1.0/fileids
```

This endpoint returns the uploaded-file records registered for the current caller.

Example:

```bash
curl --fail-with-body \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	"https://server.example.org:8444/caesar/api/v1.0/fileids"
```

Unlike older versions of the documentation, the current endpoint returns a **JSON array of file metadata objects**, rather than an object containing only a `file_ids` array.

An illustrative response is:

```json
[
  {
    "fileid": "a668c353ba4d4c7395ad94b4e8647d92",
    "filename_orig": "observation.fits",
    "fileext": "fits",
    "filesize": 4.01,
    "filedate": "2026-10-01T10:30:00",
    "metadata": "",
    "tag": "radio-image"
  }
]
```

The endpoint excludes the internal MongoDB `_id` and server-side `filepath` fields.

The results are restricted to the caller's file collection.

## 4. Download uploaded files

**Endpoint:**

```http
GET /caesar/api/v1.0/download/{file_uuid}
```

Example:

```bash
curl --fail-with-body -L \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	-o observation.fits \
	"https://server.example.org:8444/caesar/api/v1.0/download/a668c353ba4d4c7395ad94b4e8647d92"
```

On success, the endpoint returns the file as a downloadable attachment.

The implementation looks up the file UUID in the caller's MongoDB file collection. A UUID belonging to another user is not sufficient to retrieve that user's file.

If the UUID is unknown or the file is missing, the endpoint returns HTTP `404` with a JSON error message.

The legacy API also supports `GET` or `POST` requests to `/download`, supplying the UUID through a query or form parameter. New clients should prefer the explicit UUID path.

## 5. Delete uploaded files

**Endpoint:**

```http
DELETE /caesar/api/v1.0/delete/{file_uuid}
```

Example:

```bash
curl --fail-with-body -X DELETE \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	"https://server.example.org:8444/caesar/api/v1.0/delete/a668c353ba4d4c7395ad94b4e8647d92"
```

The service looks up the file in the caller's file collection, removes it from the filesystem and then deletes its metadata record from MongoDB.

On success, it returns:

```json
{
  "status": "File deleted and removed from DB"
}
```

If the file cannot be located or deleted, the endpoint returns an error.

File deletion is destructive. Clients should verify the selected UUID before issuing a delete request.

## 6. List available scientific datasets

**Endpoint:**

```http
GET /caesar/api/v1.0/datasets
```

Example:

```bash
curl --fail-with-body \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	"https://server.example.org:8444/caesar/api/v1.0/datasets"
```

The response maps dataset IDs to metadata describing the datasets available to the caller.

For example, older static deployments could return:

```json
{
  "smgps": {
    "description": "MeerKAT Galactic Plane Survey image cutouts"
  },
  "smgps-feats-simclr": {
    "description": "SimCLR representations derived from survey cutouts"
  }
}
```

The response structure depends on whether the managed dataset registry is enabled.

### Static dataset configuration

When the managed registry is disabled, the endpoint returns datasets configured statically in the application, provided they have a configured path.

This preserves compatibility with historical deployment configurations. In this mode, dataset discovery does not use the managed registry's per-user visibility and team-access rules. Administrators should therefore review which datasets are exposed through static configuration.

### Managed dataset registry

When the registry is enabled, dataset discovery applies the current caller's access permissions.

The returned list includes enabled, accessible datasets. Dataset administrators may also see statically configured datasets maintained for compatibility.

Registered dataset metadata may include the dataset name, description, type, format, visibility and allowed teams.

Dataset filesystem paths are not exposed through the public metadata response.

## 7. Managed dataset registration

Managed dataset registration requires the dataset registry to be enabled and the caller to have dataset-administrator privileges.

**Endpoint:**

```http
POST /caesar/api/v1.0/datasets
```

Example:

```bash
curl --fail-with-body -X POST \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{
		"dataset_id": "survey-images",
		"name": "Survey image collection",
		"description": "Registered scientific image dataset",
		"type": "directory",
		"path": "/storage/caesar-rest/datasets/survey-images",
		"visibility": "restricted",
		"allowed_teams": ["research-team"],
		"enabled": true
	}' \
	"https://server.example.org:8444/caesar/api/v1.0/datasets"
```

The path must be accessible to the CAESAR-REST server, satisfy its configured managed-dataset-root restrictions, and refer to an existing file or directory consistent with the declared dataset type.

The `allowed_teams` values must identify existing enabled teams. The example assumes that `research-team` has already been created.

Registration supports the following fields:

| Field | Description |
| --- | --- |
| `dataset_id` | Unique dataset identifier |
| `name` | Human-readable name |
| `description` | Optional description |
| `path` | Server-side path within an allowed managed dataset root |
| `type` | `file` or `directory`; defaults to `directory` |
| `format` | Optional format description |
| `visibility` | `public`, `restricted` or `admin`; defaults to `admin` |
| `allowed_teams` | List of permitted team identifiers |
| `enabled` | Whether the dataset is enabled |

A successful registration returns HTTP `201`:

```json
{
  "dataset_id": "survey-images",
  "inspection": {
    "status": "PENDING"
  }
}
```

A newly registered dataset receives an independent inspection record with status `PENDING`.

Registration does not perform scientific inspection synchronously. The inspection is processed by the separately configured dataset-inspection worker.

The availability of scientific inspection results depends on the detected dataset format and the inspectors supported by the deployment.

Registration may be rejected because of insufficient privileges, an invalid or inaccessible path, invalid metadata, unknown teams or a duplicate dataset ID.

A registered dataset can subsequently be selected through its dataset ID, subject to authorization.

## 8. Managed dataset metadata and lifecycle

The managed registry provides additional operations.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/datasets/me` | Return authenticated identity and registry status |
| `GET` | `/datasets/{dataset_id}` | Retrieve accessible dataset metadata |
| `PATCH` | `/datasets/{dataset_id}` | Update dataset metadata |
| `DELETE` | `/datasets/{dataset_id}` | Disable a registered dataset |
| `GET` | `/datasets/{dataset_id}/inspection` | Retrieve persisted scientific inspection status and metadata |
| `POST` | `/datasets/{dataset_id}/inspection/refresh` | Request a new asynchronous inspection; dataset-administrator access required |
| `GET` | `/datasets/{dataset_id}/targets` | Retrieve scientific targets and calibrators discovered from supported inspection metadata |

All endpoint paths in this table are relative to `/caesar/api/v1.0`.

The inspection and target-discovery endpoints require access to the registered dataset.

Reading inspection results and discovered targets does not trigger scientific processing or access the underlying dataset files. These endpoints return information already persisted by the inspection subsystem.

Inspection refresh is an administrative operation and does not perform the inspection synchronously.

For example:

```http
GET /caesar/api/v1.0/datasets/survey-images
```

returns the accessible dataset's public metadata.

The `PATCH` and `DELETE` operations require dataset-administrator privileges.

Dataset deletion is implemented as **deactivation**, not removal of the underlying scientific files.

A successful deactivation returns:

```json
{
  "dataset_id": "survey-images",
  "enabled": false
}
```

Disabled datasets are no longer available for ordinary dataset selection.

## 9. Dataset identities and team access

**Endpoint:**

```http
GET /caesar/api/v1.0/datasets/me
```

This endpoint reports the authenticated identity used by the dataset registry.

Its response includes the identity provider issuer, subject, derived storage-independent user ID, dataset-administrator status and whether the managed registry is enabled.

Team-management endpoints are also available under:

```text
/caesar/api/v1.0/teams
/caesar/api/v1.0/teams/{team_id}/members
```

These endpoints support team discovery and administrative team membership management according to the authorization checks implemented by the registry.

Team identifiers can be used in the `allowed_teams` field of restricted datasets.

The registry's access rules are authoritative. A valid bearer token alone does not grant access to restricted datasets.

## 10. Dataset selection in scientific jobs

Scientific applications may accept dataset IDs as inputs.

When the managed registry is enabled, CAESAR-REST resolves dataset IDs through the registry and checks whether the caller has permission to use the selected dataset.

Filesystem paths within managed dataset roots should not be submitted directly as substitutes for registered dataset IDs.

This distinction is particularly important for multi-user deployments and scientific pipeline automation.

See [Job submission](jobs.md), [Scientific Pipeline V2](scientific-pipelines.md) for the relevant job and pipeline submission contracts.

### Dataset association in Pipeline V2

For dataset-bound Pipeline V2 workflows, the managed dataset is specified when creating the pipeline:

```http
POST /caesar/api/v1.0/pipelines
```

Example request:

```json
{
  "app": "oxkat",
  "dataset_id": "oxkat-test-dataset-v5",
  "name": "MeerKAT calibration experiments"
}
```

The pipeline stores the authorized dataset association.

Subsequent run registrations within that dataset-bound pipeline must not repeat `dataset_id`.

The application-specific stage policy determines whether a run consumes the original dataset or retained upstream pipeline artifacts.

For OXKAT, GET_INFO and 1GC consume the registered Measurement Set according to their stage input policies, while FLAG and 2GC consume target-specific retained artifacts.

Dataset inspection, target discovery and bulk planning use this pipeline-level dataset association.

For details, see [Scientific Pipeline V2](scientific-pipelines.md).

## 11. Scientific dataset inspection

CAESAR-REST supports asynchronous scientific inspection of registered datasets.

Dataset inspection identifies supported scientific data formats and extracts metadata that can be used by downstream scientific applications and Pipeline V2 readiness providers.

Inspection is separate from dataset registration, pipeline run execution and Slurm job submission.

The inspection subsystem consists of:

- A persisted MongoDB inspection record associated with each managed dataset.
- An independent dataset-inspection worker.
- A trusted format-detection and inspector-selection mechanism.
- Container-based scientific inspectors.
- REST endpoints for inspection status, metadata retrieval, refresh and target discovery.

### 11.1 Inspection lifecycle

Newly registered datasets receive an inspection request with initial status `PENDING`.

The inspection worker claims eligible requests and processes them asynchronously.

The inspection lifecycle includes:

| Status | Description |
| --- | --- |
| `NOT_REQUESTED` | No inspection record exists, primarily for older datasets |
| `PENDING` | Inspection is awaiting processing or a scheduled retry |
| `RUNNING` | An inspection worker has claimed the request |
| `READY` | Inspection completed and scientific metadata is available |
| `FAILED` | Inspection failed and no further automatic retry is scheduled |
| `UNSUPPORTED` | No compatible inspector is available or the detected format is unsupported |

A declared format that conflicts with positively detected data is also treated as a format-selection failure.

Inspection status is independent of dataset availability and scientific pipeline execution state.

A dataset can exist and be accessible while its inspection is still pending or unsuccessful.

The worker uses atomic MongoDB claims, generation identifiers and leases to protect against concurrent processing and stale updates.

Transient infrastructure failures can be retried with bounded backoff. Expired worker claims can be recovered without reclaiming active, unexpired leases.

### 11.2 Retrieve inspection status and metadata

**Endpoint:**

```http
GET /caesar/api/v1.0/datasets/{dataset_id}/inspection
```

The request requires authentication and access to the managed dataset.

Example:

```bash
curl --fail-with-body \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    "https://server.example.org:8444/caesar/api/v1.0/datasets/oxkat-test-dataset-v5/inspection"
```

The response contains persisted inspection information.

Common fields include:

| Field | Description |
| --- | --- |
| `dataset_id` | Inspected dataset |
| `status` | Current inspection lifecycle status |
| `attempt` | Number of worker processing attempts |
| `requested_at` | Inspection request timestamp |
| `started_at` | Worker processing start timestamp |
| `finished_at` | Completion timestamp, when available |
| `last_checked_at` | Last recorded source-freshness check |
| `detected_format` | Detected scientific data format |
| `declared_format` | Normalized declared format |
| `detection_evidence` | Evidence used for format detection |
| `inspector` | Selected scientific inspector |
| `schema` | Inspection metadata schema identifier |

When status is `READY`, the response additionally includes:

- `metadata`: scientific metadata extracted by the inspector.
- `source_fingerprint`: source identity information used by the inspection lifecycle.

When status is `FAILED`, the detailed error is included only for dataset administrators.

Internal worker claim tokens, leases and registered filesystem paths are not exposed.

Retrieving inspection status is read-only and does not execute the scientific inspector.

### 11.3 Request inspection refresh

**Endpoint:**

```http
POST /caesar/api/v1.0/datasets/{dataset_id}/inspection/refresh
```

Only dataset administrators may request an inspection refresh.

An inspection refresh creates a new inspection generation and resets the dataset inspection state to `PENDING`.

Example:

```bash
curl --fail-with-body -X POST \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    "https://server.example.org:8444/caesar/api/v1.0/datasets/oxkat-test-dataset-v5/inspection/refresh"
```

A successful request returns HTTP `202`.

Example response:

```json
{
  "dataset_id": "oxkat-test-dataset-v5",
  "status": "PENDING",
  "requested_at": "2026-11-04T10:00:00+00:00"
}
```

The timestamp is illustrative.

Refresh is accepted when the previous inspection is `READY`, `FAILED`, `UNSUPPORTED` or `NOT_REQUESTED`.

A refresh request is rejected with HTTP `409` when inspection is already `PENDING` or `RUNNING`, or when a concurrent inspection-state change prevents the requested update.

The endpoint does not execute inspection synchronously.

Changing the registered dataset's declared `format` also creates a new pending inspection generation.

### 11.4 Scientific format detection and inspectors

The inspection subsystem selects inspectors using server-controlled configuration and detected scientific data format.

A declared dataset format is not by itself sufficient to establish the actual scientific format.

The current default inspector registry includes a local container-backed inspector for CASA Measurement Set V2 datasets.

Its metadata schema is:

```text
caesar.dataset-inspection.msv2.v1
```

The configured inspector performs scientific metadata extraction using an isolated execution environment.

Additional formats require corresponding trusted inspector implementations and deployment configuration.

Unsupported formats are not silently interpreted as valid Measurement Sets.

A mismatch between positively detected content and the declared dataset format is rejected rather than ignored.

### 11.5 Discover scientific targets

**Endpoint:**

```http
GET /caesar/api/v1.0/datasets/{dataset_id}/targets
```

The endpoint returns scientific field discovery information derived from persisted inspection metadata.

It requires authentication and access to the dataset.

Example:

```bash
curl --fail-with-body \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    "https://server.example.org:8444/caesar/api/v1.0/datasets/oxkat-test-dataset-v5/targets"
```

For a dataset whose inspection is not `READY`, the response reports the dataset ID and current inspection status.

For a completed supported Measurement Set inspection, the response includes:

| Field | Description |
| --- | --- |
| `dataset_id` | Dataset identifier |
| `status` | Inspection status |
| `detected_format` | Detected scientific format |
| `inspection_schema` | Inspection metadata schema |
| `field_observations_available` | Whether field observation metadata is available |
| `fields_truncated` | Whether field reporting was truncated |
| `main_rows_scanned` | Number of main-table rows inspected |
| `rows_with_unreported_field` | Rows referencing fields not included in the reported inventory |
| `counts` | Counts of science targets, calibrators and unclassified fields |
| `science_targets` | Discovered science target records |
| `calibrators` | Discovered calibrator records |
| `unclassified_fields` | Fields not classified as science targets or calibrators |

Each returned field record includes:

- `field_id`
- `name`
- `classification`
- `observation_intents`
- `scan_count`
- `scan_count_truncated`
- `visibility_row_count`

Field records are ordered by numeric `field_id` within their respective categories.

For supported Measurement Set inspections, the `classification` field distinguishes science targets, calibrators and unclassified fields.

The endpoint validates the persisted inspection metadata before returning the target inventory.

If a `READY` inspection has an unsupported schema, unavailable field observations or invalid stored metadata, the request fails rather than returning an invented target list.

Target discovery does not reopen the Measurement Set or run the inspector.

### 11.6 Dataset inspection and Pipeline V2

Dataset inspection supports application-specific scientific readiness and target-aware pipeline planning.

For OXKAT, inspection identifies the science fields associated with an original MeerKAT Measurement Set.

An orchestration client can:

1. Retrieve the registered dataset metadata.
2. Check the dataset inspection status.
3. Retrieve the scientific target inventory when inspection is `READY`.
4. Create or inspect a dataset-bound OXKAT pipeline.
5. Query pipeline scientific readiness.
6. Plan eligible target-specific FLAG or 2GC registrations.
7. Register and execute those runs independently.

The relevant Pipeline V2 endpoints are:

```http
GET /caesar/api/v1.0/pipelines/{pipeline_id}/scientific-readiness
POST /caesar/api/v1.0/pipelines/{pipeline_id}/bulk-plan
POST /caesar/api/v1.0/pipelines/{pipeline_id}/bulk-register
```

A completed dataset inspection does not imply that scientific processing stages are ready.

For example, OXKAT FLAG readiness also requires suitable selected and retained 1GC artifacts.

Likewise, 2GC requires eligible upstream FLAG products.

For target-aware OXKAT planning, incomplete field-observation metadata can prevent reliable scientific readiness even when the inspection status is `READY`.

Inspection metadata is used for discovery and scientific planning; actual pipeline run registration performs authoritative input validation and immutable artifact binding.

See [Scientific Pipeline V2](scientific-pipelines.md) and the [MAASAI orchestration contract](../maasai_orchestration_contract.md).

## References

- [REST API overview](overview.md)
- [Job submission and monitoring](jobs.md)
- [Scientific Pipeline V2](scientific-pipelines.md)
- [Keycloak and OpenID Connect authentication](../deployment/authentication.md)
- [Application discovery and self-description](applications.md)
- [MAASAI Pipeline V2 orchestration contract](../maasai_orchestration_contract.md)
- [Archived original README](../archive/ORIGINAL_README.md)
