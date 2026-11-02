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

For managed datasets, clients should use dataset IDs rather than supplying arbitrary filesystem paths.

## 2. Upload files

<text weight="medium">Endpoint:</text>

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

A successful response has the following structure:

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

<text weight="medium">Endpoint:</text>

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

<text weight="medium">Endpoint:</text>

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

<text weight="medium">Endpoint:</text>

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

<text weight="medium">Endpoint:</text>

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

When the managed registry is disabled, the endpoint returns the available datasets configured in the application.

This preserves compatibility with historical deployment configurations.

### Managed dataset registry

When the registry is enabled, dataset discovery applies the current caller's access permissions.

The returned list includes enabled, accessible datasets. Dataset administrators may also see statically configured datasets maintained for compatibility.

Registered dataset metadata may include the dataset name, description, type, format, visibility and allowed teams.

Dataset filesystem paths are not exposed through the public metadata response.

## 7. Managed dataset registration

Managed dataset registration requires the dataset registry to be enabled and the caller to have dataset-administrator privileges.

<text weight="medium">Endpoint:</text>

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
		"path": "/storage/caesar-rest/datasets/s
