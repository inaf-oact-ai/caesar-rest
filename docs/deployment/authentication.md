# Keycloak and OpenID Connect authentication

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 635–970). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

### Keycloak / OpenID Connect Authentication (AAI)

CAESAR-REST supports OpenID Connect (OIDC) authentication through Keycloak. When AAI is enabled, the application supports two authentication mechanisms:

- **Interactive browser authentication**, using the OIDC Authorization Code Flow.
- **REST API authentication**, using OAuth2 bearer access tokens validated through Keycloak token introspection.

Both authentication mechanisms have been successfully tested against Keycloak with the `caesar` realm.

#### Architecture

The tested deployment consists of:

| Component | Configuration |
|---|---|
| Keycloak server | `https://[KEYCLOAK_HOST]:8443` |
| Keycloak realm | `caesar` |
| CAESAR-REST service | `https://[CAESAR_REST_HOST]:8444` |
| Browser/OIDC client | `caesar-rest` |
| External API testing client | `insomnia-caesar` |
| Authentication library | `flask-oidc-ex` (INAF fork) |
| API token validation | Keycloak token introspection |

The deployment URLs are examples from the validated installation and should be replaced when deploying to another environment.

#### OIDC Python dependency

CAESAR-REST uses a custom fork of `flask-oidc-ex`:

https://github.com/inaf-oact-ai/flask-oidc-ex

The original library contains an incompatibility with recent Werkzeug versions: its OIDC cookie serializer can return a `bytes` value, while `response.set_cookie()` expects a string.

Our fork fixes the issue by converting the serialized cookie to UTF-8 when necessary:

```python
signed_id_token = self.cookie_serializer.dumps(g.oidc_id_token)

if isinstance(signed_id_token, bytes):
	signed_id_token = signed_id_token.decode('utf-8')
```

The fork must be installed instead of the original PyPI package.

The CAESAR-REST dependency declarations in `setup.py` and `requirements.txt` should reference:

```text
flask-oidc-ex @ git+https://github.com/inaf-oact-ai/flask-oidc-ex.git@master
```

For an existing installation, the dependency can be updated with:

```bash
python -m pip install --upgrade --no-deps \
  "flask-oidc-ex @ git+https://github.com/inaf-oact-ai/flask-oidc-ex.git@master"
```

Using `@master` retrieves the latest available code when the package is explicitly installed or upgraded; it does not automatically update existing environments. Production deployments requiring exact reproducibility can pin a specific Git commit or release tag.

Manual modification of files under Python's `site-packages` directory is not required.

#### Keycloak client configuration

**Client: `caesar-rest`**

This client is used for interactive browser login and token introspection.

Recommended configuration:

| Setting | Value |
|---|---|
| Client ID | `caesar-rest` |
| Client authentication | ON |
| Standard Flow | ON |
| Service Accounts | OFF |
| Valid redirect URI | `https://[CAESAR_REST_HOST]:8444/oidc_callback` |
| Web origin | `https://[CAESAR_REST_HOST]:8444` |

The client secret must be stored securely and referenced in CAESAR-REST's OIDC client configuration. 

**Client: `insomnia-caesar`**

This client is used by Insomnia and other interactive API testing workflows.

| Setting | Value |
|---|---|
| Client ID | `insomnia-caesar` |
| Client authentication | OFF |
| Standard Flow | ON |
| PKCE Code Challenge Method | `S256` |
| Valid redirect URI | `http://localhost` (for the tested Insomnia configuration) |
| OAuth scopes | `openid profile email` |

The Insomnia client is public and does not require a client secret.

The OAuth2 Device Authorization Grant is not required for the tested Authorization Code + PKCE workflow.

#### Configure access-token audiences

Access tokens issued through `insomnia-caesar` must identify CAESAR-REST as an intended audience.

Without this configuration, tokens may contain:

```json
{
  "aud": "account",
  "azp": "insomnia-caesar"
}
```

Keycloak can reject introspection by `caesar-rest` for such tokens, returning:

```json
{
  "active": false
}
```

To configure the correct audience:

1. Open the Keycloak Admin Console.
2. Navigate to **Clients → insomnia-caesar → Client scopes**.
3. Open `insomnia-caesar-dedicated`.
4. Select **Mappers → Configure a new mapper → Audience**.
5. Set **Included Client Audience** to `caesar-rest`.
6. Enable **Add to access token**.
7. Save the mapper and obtain a new access token.

A correctly configured token contains an audience similar to:

```json
{
  "aud": ["caesar-rest", "account"],
  "azp": "insomnia-caesar"
}
```

In the validated deployment, this change allowed token introspection to return `"active": true`.

Other OAuth clients calling CAESAR-REST may also need an appropriate audience configuration.

#### Configure TLS certificate trust

The legacy `flask-oidc-ex` library uses `httplib2` for some HTTPS requests to Keycloak.

On the tested Ubuntu deployment, OpenSSL successfully validated the Keycloak server certificate using the system CA trust store, but the CA bundle selected by `httplib2`/`certifi` did not contain the necessary trusted issuer.

This caused the browser OIDC callback to fail with:

```text
ssl.SSLCertVerificationError:
[SSL: CERTIFICATE_VERIFY_FAILED]
unable to get local issuer certificate
```

On Ubuntu, the issue was resolved by configuring `httplib2` to use the system CA certificate bundle:

```bash
export HTTPLIB2_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
```

For other operating systems or container images, use the corresponding trusted CA bundle path.

This environment variable must be available to the CAESAR-REST application process **before it starts**.

It can be configured in the application launch script or through systemd:

```ini
[Service]
Environment="HTTPLIB2_CA_CERTS=/etc/ssl/certs/ca-certificates.crt"
```

Restart CAESAR-REST after applying the configuration.

To verify the CA bundle independently:

```bash
python - <<'PY'
import httplib2

url = "https://[KEYCLOAK_HOST]:8443/realms/caesar/.well-known/openid-configuration"

http = httplib2.Http(
	ca_certs="/etc/ssl/certs/ca-certificates.crt"
)

response, content = http.request(url)
print("HTTP status:", response.status)
PY
```

Expected result:

```text
HTTP status: 200
```

Do not disable certificate verification in the CAESAR-REST application as a workaround.

#### Enable authentication in CAESAR-REST

Start CAESAR-REST with AAI enabled, providing the appropriate OIDC client-secrets configuration and realm.

Relevant application options are:

```text
--aai
--secretfile=<PATH_TO_CLIENT_SECRETS_JSON>
--openid_realm=caesar
```

The client-secrets JSON must describe the `caesar-rest` OIDC client and contain the appropriate Keycloak endpoints and client credentials.

The `caesar-rest` client is confidential and should use secure secret storage.

CAESAR-REST initializes the OIDC integration through:

```python
oidc.init_app(app)
```

The `custom_require_browser_login` decorator is used for interactive browser authentication, while `custom_require_login` validates REST API bearer tokens.

These mechanisms must remain separate: interactive login redirects the user to Keycloak, whereas REST authentication returns an HTTP authorization error when the bearer token is missing or invalid.

#### Test browser authentication

Open:

```text
https://[CAESAR_REST_HOST]:8444/login
```

Expected authentication flow:

1. CAESAR-REST redirects the browser to Keycloak.
2. The user authenticates in the `caesar` realm.
3. Keycloak redirects the browser to `/oidc_callback`.
4. CAESAR-REST exchanges the authorization code for tokens.
5. The OIDC session cookie is created.
6. The browser returns to the CAESAR-REST index page.

#### Test REST API authentication

Obtain an access token through an authorized OAuth2 client using Authorization Code + PKCE.

The token should contain:

- `iss`: the Keycloak realm URL.
- `sub`: the authenticated user's stable subject identifier.
- `aud`: including `caesar-rest`.
- `azp`: the OAuth2 client that requested the token.
- `exp`: token expiration time.

Then use the access token to call a protected CAESAR-REST endpoint:

```bash
read -r -s -p "Access token: " ACCESS_TOKEN
echo

curl -i -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/json" \
  "https://[CAESAR_REST_HOST]:8444/caesar/api/v1.0/apps"

unset ACCESS_TOKEN
```

Expected HTTP response:

```text
HTTP/1.1 200 OK
```

The response contains the list of available CAESAR-REST applications.

The same endpoint can be used to verify authentication failures:

```bash
curl -i \
  "https://[CAESAR_REST_HOST]:8444/caesar/api/v1.0/apps"
```

Without a token, the endpoint should return HTTP 401 when AAI is enabled.

Invalid or expired bearer tokens should also be rejected with HTTP 401.

These API tests have been successfully performed using both Insomnia and `curl`.

#### Token introspection

CAESAR-REST's current authentication library uses online token validation by default.

Tokens are introspected using the confidential `caesar-rest` client at:

```text
https://[KEYCLOAK_HOST]:8443/realms/caesar/protocol/openid-connect/token/introspect
```

For an active token with the correct audience, Keycloak returns a response containing:

```json
{
  "active": true,
  "iss": "https://[KEYCLOAK_HOST]:8443/realms/caesar",
  "aud": ["caesar-rest", "account"],
  "azp": "insomnia-caesar"
}
```

The complete response also includes subject and other token claims.

CAESAR-REST exposes validated claims to its endpoints through `g.oidc_token_info`.

The dataset registry uses the verified issuer and subject (`iss` and `sub`) to establish stable user identity.

#### Insomnia compatibility note

The tested Insomnia version was `2023.3.0` on Ubuntu.

Authorization Code + PKCE worked after correcting the PKCE challenge method, but OAuth2 token fetching encountered:

```text
SSL peer certificate or SSH remote key was not OK
```

Ordinary HTTPS requests and command-line `curl` certificate validation worked correctly.

Insomnia successfully retrieved the token when its **Validate certificates during authentication** setting was disabled, indicating a certificate-trust issue specific to its authentication transport.

**Disabling certificate verification is an insecure diagnostic workaround, not a recommended permanent configuration.**

For normal use, certificate validation should remain enabled. Upgrade Insomnia or fix its authentication-specific certificate trust configuration before using it for sensitive credentials.

The working CAESAR-REST API authentication can be verified independently using `curl`.

