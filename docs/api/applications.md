# Application discovery REST API

CAESAR-REST provides REST endpoints for discovering available scientific applications and retrieving their supported execution options.

Application discovery allows clients to inspect the applications registered in the current server configuration before submitting scientific jobs.

All endpoints use the base path `/caesar/api/v1.0`. When authentication is enabled, requests require a valid OAuth 2.0 bearer access token.

See [REST API overview](overview.md) and [Keycloak authentication](../deployment/authentication.md).

## 1. List available applications

**Endpoint:**

```http
GET /caesar/api/v1.0/apps
```

This endpoint returns the names of scientific applications registered with the CAESAR-REST job configurator.

Example:

```bash
curl --fail-with-body \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	"https://server.example.org:8444/caesar/api/v1.0/apps"
```

The response is a JSON object containing an `apps` array.

An illustrative response is:

```json
{
  "apps": [
    "caesar",
    "aegean",
    "umap",
    "hdbscan",
    "fextractor",
    "oxkat"
  ]
}
```

The example is illustrative, not an exhaustive or guaranteed list of applications in a particular deployment.

The actual application list is generated dynamically from the server's registered application configurators. It may change as applications are added, removed or updated.

Clients should use this endpoint rather than maintaining a hardcoded list of supported application names.

An application appearing in this list means that its configurator is registered. It does not necessarily guarantee that its scientific container image, external dependencies or execution backend have been successfully validated in the current deployment.

## 2. Retrieve an application description

**Endpoint:**

```http
GET /caesar/api/v1.0/app/{app_name}/describe
```

Replace `{app_name}` with an application name returned by the discovery endpoint.

For example:

```bash
curl --fail-with-body \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	"https://server.example.org:8444/caesar/api/v1.0/app/umap/describe"
```

The endpoint obtains the application's description from its registered configurator.

The response is a JSON dictionary describing available application parameters.

A representative subset of the historical UMAP description is:

```json
{
  "mindist": {
    "advanced": 0,
    "category": "PROCESSING",
    "default": 0.1,
    "description": "Min dist UMAP parameter (default=0.1)",
    "enum": false,
    "mandatory": false,
    "max": 1.0,
    "min": 0.0,
    "subcategory": "",
    "type": "float"
  },
  "nneighbors": {
    "advanced": 0,
    "category": "PROCESSING",
    "default": 15,
    "description": "N neighbors UMAP parameter (default=15)",
    "enum": false,
    "mandatory": false,
    "max": 10000,
    "min": 1,
    "subcategory": "",
    "type": "int"
  }
}
```

This is an abbreviated historical example. The installed application configurator determines the actual fields, defaults and supported parameters.

The original, more extensive UMAP description remains available in the [archived README](../archive/ORIGINAL_README.md).

### Option metadata

Application option descriptions may include:

| Field | Meaning |
| --- | --- |
| `type` | Expected option value type |
| `description` | Human-readable parameter description |
| `default` | Default value, when defined |
| `mandatory` | Whether the option is required |
| `min` | Minimum accepted value, when applicable |
| `max` | Maximum accepted value, when applicable |
| `enum` | Enumeration information, where supported |
| `category` | Functional category, such as `INPUT`, `PROCESSING` or `OUTPUT` |
| `subcategory` | More specific option grouping |
| `advanced` | Indicator used to distinguish advanced options |

Not every option necessarily defines every metadata field.

Some scientific application options represent command-line flags and therefore do not accept an ordinary scalar value.

Clients should interpret the returned metadata according to the application-specific contract rather than assuming that every option is a numeric or string parameter.

## 3. Unknown applications

If an unknown application name is supplied, the description endpoint returns HTTP `400`.

An illustrative response is:

```json
{
  "status": "Unknown app unknown-application!"
}
```

Clients should check the application list before attempting to retrieve a description or submit a job.

## 4. Application discovery and job submission

Application discovery and scientific job submission are separate operations.

The discovery endpoints describe the applications registered with CAESAR-REST. Jobs are submitted through:

```http
POST /caesar/api/v1.0/job
```

The job submission request identifies the application and provides its required inputs and execution options.

The server applies application-specific validation and constructs the scientific execution request using the corresponding configurator.

Clients should not assume that all registered applications accept identical inputs, output formats or execution options.

See [Job submission and monitoring](jobs.md) for the job request and response contract.

## 5. Application-specific scientific configuration

Some scientific applications support additional scientific configuration beyond ordinary scalar command-line parameters.

These options may depend on the selected scientific stage, execution mode or application-specific validation rules.

### OxKAT and Scientific Pipeline V2

The OxKAT configurator supports stage-specific scientific configuration overrides in Pipeline V2.

Its V2 `job_options` include a required stage selection and may include an `oxkat_config` object containing scientific configuration overrides.

For example, the application-specific options conceptually have the form:

```json
{
  "stage": "1GC",
  "oxkat_config": {
    "OPTION_NAME": "OPTION_VALUE"
  }
}
```

`OPTION_NAME` and `OPTION_VALUE` are placeholders, not actual OxKAT parameters.

CAESAR-REST validates the override names, values and applicability to the selected pipeline stage. Invalid or stage-incompatible options are rejected before execution.

These settings are processed by the OxKAT-specific configurator rather than being accepted as arbitrary command-line arguments.

The example above illustrates only the application-specific `job_options` object; it is not a complete Pipeline V2 job submission payload.

For the complete submission contract, see the [Scientific Pipeline API reference](scientific-pipelines.md).

## 6. Client integration recommendations

Clients integrating with CAESAR-REST should retrieve available application names and descriptions from the running server.

Application-option metadata can be used to construct forms, populate defaults and provide basic client-side validation.

However, server-side validation remains authoritative, particularly for scientific options with stage-dependent rules.

For automated scientific pipelines, clients must also follow the pipeline run and artifact lifecycle described by the Pipeline V2 API.

Application discovery does not replace pipeline registration, run reservation, job submission or artifact retention.

## References

- [REST API overview](overview.md)
- [Data and datasets API](data.md)
- [Job submission and monitoring](jobs.md)
- [Scientific Pipeline concepts, detailed API reference and examples](scientific-pipelines.md)
- [MAASAI integration](../maasai_integration.md)
- [Archived original README](../archive/ORIGINAL_README.md)
