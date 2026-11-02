# Data and datasets REST API

CAESAR-REST provides endpoints for uploading, listing, downloading and deleting user files, as well as discovering and managing scientific datasets.

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
  "dataset_id": "survey-images"
}
```

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

All endpoint paths in this table are relative to `/caesar/api/v1.0`.

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

See [Job submission](jobs.md), [Scientific Pipeline V2](scientific-pipelines.md) and the [detailed Pipeline V2 reference](../pipeline_v2_api.md) for the relevant job and pipeline submission contracts.

## References

- [REST API overview](overview.md)
- [Job submission and monitoring](jobs.md)
- [Scientific Pipeline V2](scientific-pipelines.md)
- [Detailed Pipeline V2 API reference](../pipeline_v2_api.md)
- [Keycloak and OpenID Connect authentication](../deployment/authentication.md)
- [Archived original README](../archive/ORIGINAL_README.md)
