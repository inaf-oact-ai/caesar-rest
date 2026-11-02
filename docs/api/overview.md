# REST API overview and authentication

CAESAR-REST exposes a REST API for managing scientific datasets, discovering supported applications, submitting and monitoring scientific jobs, and orchestrating multi-stage scientific pipelines.

The API supports both interactive applications and programmatic clients, including external scientific workflow systems such as MAASAI.

## 1. API base URL

The REST API uses the following base path:

```text
/caesar/api/v1.0
```

For example, a deployment accessible at `https://server.example.org:8444` exposes its application discovery endpoint at:

```http
GET https://server.example.org:8444/caesar/api/v1.0/apps
```

The hostname and port depend on the deployment configuration. See [Web application deployment](../deployment/web-application.md).

The `/caesar/api/v1.0` prefix is used by the core API and Scientific Pipeline V2 endpoints. Interactive browser routes, such as `/login` and `/oidc_callback`, are separate from the REST API namespace.

## 2. Authentication

CAESAR-REST supports authentication through Keycloak and OpenID Connect (OIDC).

Authentication is enabled by starting the REST application with the `--aai` option and configuring the corresponding OIDC client and identity provider.

When authentication is enabled, protected REST endpoints require a valid OAuth 2.0 access token in the HTTP `Authorization` header:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

Clients must obtain the access token from the configured identity provider before making protected API requests.

An example request is:

```bash
curl -i \
	-H "Authorization: Bearer ${ACCESS_TOKEN}" \
	-H "Accept: application/json" \
	"https://server.example.org:8444/caesar/api/v1.0/apps"
```

The access token must be valid for the configured CAESAR-REST identity provider and accepted by the application's authentication mechanism. An ID token should not be substituted for an API access token.

Protected API endpoints do not rely on interactive browser-login redirects. Requests without a valid bearer token are rejected when authentication is required.

For detailed instructions on configuring Keycloak, obtaining tokens and testing API authentication, see [Keycloak and OpenID Connect authentication](../deployment/authentication.md).

### Authentication and resource authorization

Authentication establishes the identity of the caller. Authorization determines which operations and resources that identity may access.

CAESAR-REST applies ownership and access-control rules to managed resources such as datasets and scientific jobs.

A successfully authenticated user is not automatically authorized to access resources owned by another user.

For multi-user deployments, clients should consistently authenticate using the intended identity and must not assume that knowledge of a dataset ID or job ID grants permission to access it.

### Deployments without authentication

CAESAR-REST can also run with authentication disabled.

However, disabling AAI does not automatically make all resource-management operations available anonymously. Some operations require authenticated ownership or depend on identity information provided by the authentication layer.

Authentication-enabled deployment is recommended for multi-user and externally accessible services.

## 3. Request and response conventions

The REST API uses standard HTTP methods, including:

| Method | Typical purpose |
| --- | --- |
| `GET` | Retrieve information, status or available resources |
| `POST` | Submit jobs, create resources or perform supported actions |

Additional methods and endpoint-specific behavior are documented in the corresponding API guides.

Many endpoints exchange JSON request and response bodies. Clients should use the appropriate HTTP headers for each operation, for example:

```http
Accept: application/json
Content-Type: application/json
```

File-upload and file-download endpoints may use different content types or multipart request formats.

### HTTP status codes

API clients should inspect both the HTTP response status and the returned response body.

Common status codes include:

| Status | Meaning |
| --- | --- |
| `200 OK` | Request completed successfully |
| `201 Created` | Resource successfully created, where used |
| `400 Bad Request` | Invalid or unsupported request |
| `401 Unauthorized` | Missing or invalid authentication credentials |
| `403 Forbidden` | Authenticated caller lacks permission |
| `404 Not Found` | Requested resource or endpoint is unavailable |
| `500 Internal Server Error` | Unexpected server-side failure |

This table describes general HTTP conventions, not a guarantee that every CAESAR-REST endpoint implements every listed status code.

Individual endpoints may also report scientific execution states, validation failures or application-specific errors in their JSON response bodies.

Clients must distinguish HTTP request success from the scientific execution status of a submitted job.

For example, successful submission does not imply that the scientific job has completed successfully.

## 4. Core REST resources

The core API includes operations for:

- [Data upload, download and dataset management](data.md)
- [Scientific application discovery and options](applications.md)
- [Job submission, monitoring, output retrieval and cancellation](jobs.md)

These guides document the endpoint-specific request parameters, response formats and usage examples.

## 5. Scientific Pipeline V2

Scientific Pipeline V2 extends CAESAR-REST with explicit pipeline and run management, artifact registration, retained outputs and controlled consumption of upstream artifacts.

Pipeline clients can register scientific workflows, create runs, inspect execution states and coordinate downstream stages.

The relevant documentation is available in:

- [Scientific Pipeline V2 concepts and examples](scientific-pipelines.md)
- [Scientific Pipeline V2 detailed API reference](../pipeline_v2_api.md)
- [MAASAI integration guide](../maasai_integration.md)

Scientific execution status and artifact readiness are distinct concepts. A successfully completed scientific run may still require artifact registration and retention before its outputs can be used by subsequent pipeline stages.

## 6. API compatibility

CAESAR-REST retains historical API operations alongside more recent dataset-management and scientific pipeline interfaces.

Clients should verify endpoint availability, request parameters and response fields against the installed CAESAR-REST version.

For Pipeline V2 integrations, use the detailed Pipeline V2 reference as the primary description of the supported contract.

Historical examples remain available in the [archived original README](../archive/ORIGINAL_README.md).

## References

- [REST API index](index.md)
- [Web application deployment](../deployment/web-application.md)
- [Keycloak and OpenID Connect authentication](../deployment/authentication.md)
- [Scientific Pipeline V2 API reference](../pipeline_v2_api.md)
- [MAASAI integration guide](../maasai_integration.md)
