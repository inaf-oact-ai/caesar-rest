# REST API introduction and authentication

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 1458–1468). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

## **Usage**  
caesar-rest provides the following REST endpoints:   

**Authentication:** When AAI is enabled, REST API requests must include a valid OAuth2 bearer access token in the `Authorization` header:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

Unless otherwise specified, the endpoint examples below assume AAI is disabled. For authenticated deployments, include the authorization header as described in the [Keycloak / OpenID Connect Authentication](#keycloak--openid-connect-authentication-aai) section.

