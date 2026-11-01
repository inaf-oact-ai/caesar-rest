# Keycloak and OpenID Connect authentication

CAESAR-REST supports interactive browser login and REST API bearer-token authentication through Keycloak and OpenID Connect (OIDC). This guide describes a Docker Compose deployment of Keycloak with PostgreSQL, Nginx TLS termination, internal-CA certificates, client configuration, CAESAR-REST integration, and validation.

Paths and network endpoints are deployment examples, not universal defaults. Commands assume an Ubuntu/Debian-like Docker host unless stated otherwise. Pin container image versions, protect environment files and database volumes, and adapt DNS names, operating system and security policies before deployment.

## Architecture and example deployment

| Component | Tested deployment | Role |
| --- | --- | --- |
| Keycloak HTTPS endpoint | `https://KEYCLOAK_HOSTNAME:8443` | OIDC identity provider, behind Nginx |
| Keycloak internal upstream | `http://127.0.0.1:8081` | Local-only Keycloak listener behind Nginx |
| Realm | `caesar` | CAESAR-REST users and clients; distinct from the `maasai` realm |
| Confidential OIDC client | `caesar-rest` | Browser login, server-side code exchange, token introspection |
| Public OIDC client | `insomnia-caesar` | API testing with Authorization Code + PKCE |
| CAESAR-REST HTTPS endpoint | `https://CAESAR_REST_HOSTNAME:8444` | Nginx reverse proxy to uWSGI |
| CAESAR-REST browser callback | `/oidc_callback` | OIDC authorization-code response |
| Server certificate | `/etc/caesar-pki/keycloak/keycloak.crt` | Example X.509 certificate for the HTTPS virtual hosts |
| Server private key | `/etc/caesar-pki/keycloak/keycloak.key` | TLS private key; never distribute to clients |
| Internal CA certificate | `/etc/caesar-pki/ca/ca.crt` | Trusted CA public certificate |
| CA private key | `/etc/caesar-pki/ca/ca.key` | Highly sensitive CA signing key |

A **realm** is the security domain; a **client** represents an OAuth/OIDC application; and a **user** is the identity authenticating through a client. The same user may authenticate through `caesar-rest` in a browser and through `insomnia-caesar` in an API-testing tool.

CAESAR-REST uses two distinct flows:

1. **Browser login:** `/login` redirects to Keycloak, returns through `/oidc_callback`, and establishes a browser session.
2. **REST API:** callers obtain an OAuth access token and send it in `Authorization: Bearer ...`; CAESAR-REST validates that token and applies resource authorization.

> **NB**: By default, the application (`run_app.py`) can run without authentication. In this case, dataset registry operations requiring authenticated ownership are not thereby made anonymous. To enable authentication, you must run the application with `--aai` option.

## 1. Install Keycloak

This section describes how to deploy Keycloak with PostgreSQL using Docker Compose and expose its authentication services securely through Nginx.

### 1.1 Install Docker Engine and Compose

Install Docker Engine and the Docker Compose plugin using your distribution's supported packages or the [official Docker installation instructions](https://docs.docker.com/engine/install/). Confirm that the Compose V2 command is available:

```bash
docker --version
docker compose version
```

Store the Keycloak deployment configuration and credentials outside the public CAESAR-REST Git repository. The deployment directory will be created in Section 1.2.

### 1.2 Configure the Keycloak service

Create a directory for the Keycloak Docker Compose deployment. The following example uses `/opt/keycloak/caesar`:

```bash
sudo mkdir -p /opt/keycloak/caesar
```

Create `/opt/keycloak/caesar/.env` containing values generated specifically for this installation:

```dotenv
KEYCLOAK_DB=keycloak
KEYCLOAK_DB_USER=keycloak
KEYCLOAK_DB_PASSWORD=REPLACE_WITH_STRONG_DATABASE_PASSWORD
KEYCLOAK_ADMIN_USER=REPLACE_WITH_ADMIN_NAME
KEYCLOAK_ADMIN_PASSWORD=REPLACE_WITH_STRONG_ADMIN_PASSWORD
KEYCLOAK_HOST=https://server.example.org:8443
```

Replace `server.example.org` with the actual FQDN before starting the containers.

Restrict access:

```bash
sudo chmod 600 /opt/keycloak/caesar/.env
```

The bootstrap administrator credentials are for initial setup. After creating and testing a permanent administrative account, remove the bootstrap password from the long-lived deployment configuration where operationally feasible. Do not publish this file or commit it to Git. Docker environment variables may be visible to administrators with Docker access; use secret-management facilities if stronger protections are required.

Create a Docker compose file `/opt/keycloak/caesar/docker-compose.yaml` containing Keycloak configuration:

```yaml
services:

  keycloak-db:
    image: postgres:17
    container_name: caesar-keycloak-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${KEYCLOAK_DB}
      POSTGRES_USER: ${KEYCLOAK_DB_USER}
      POSTGRES_PASSWORD: ${KEYCLOAK_DB_PASSWORD}
    volumes:
      - keycloak_postgres_data:/var/lib/postgresql/data

  keycloak:
    image: quay.io/keycloak/keycloak:26.8.0
    container_name: caesar-keycloak
    restart: unless-stopped
    command:
      - start
      - --hostname=${KEYCLOAK_HOST}
      - --http-enabled=true
      - --proxy-headers=xforwarded
    environment:
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak
      KC_DB_USERNAME: ${KEYCLOAK_DB_USER}
      KC_DB_PASSWORD: ${KEYCLOAK_DB_PASSWORD}
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KEYCLOAK_ADMIN_USER}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD}
      KC_HOSTNAME: ${KEYCLOAK_HOST}
      KC_HTTP_ENABLED: "true"
      KC_PROXY_HEADERS: xforwarded   
    depends_on:
      - keycloak-db
    ports:
        - "127.0.0.1:8081:8080"

volumes:
  keycloak_postgres_data:
```

This example uses a persistent Docker volume. Verify the appropriate PostgreSQL data-directory layout before upgrading across major PostgreSQL releases, and back up database contents prior to changing either image version. For stricter reproducibility, pin images to validated digests in addition to documenting their tags.

Keycloak is started in production mode (`start`), with **HTTP enabled only between Nginx and the loopback-bound Docker port**. Public HTTPS is terminated by Nginx. Do not replace `start` with `start-dev` in production. Keycloak's `KC_HOSTNAME` must include the externally visible scheme and port so issuer URLs and redirects remain correct.

### 1.3 Start and verify the containers

```bash
cd /opt/keycloak/caesar
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
```

The reference deployment runs two containers:

| Container | Image | Published ports | Purpose |
| --- | --- | --- | --- |
| `caesar-keycloak` | `quay.io/keycloak/keycloak:26.8.0` | `127.0.0.1:8081:8080` | Keycloak, accessible only through the local Nginx reverse proxy |
| `caesar-keycloak-db` | `postgres:17` | None | Dedicated persistent Keycloak database |

Inspect service logs with:

```bash
docker logs --tail 100 caesar-keycloak
docker logs --tail 100 caesar-keycloak-db
curl --fail-with-body -sS http://127.0.0.1:8081/realms/master/.well-known/openid-configuration
```

The database port `5432` should **not** be published to the host, and Keycloak port `8080` should be published only on `127.0.0.1:8081`. The Keycloak management port `9000` should not be publicly exposed. Review firewall rules and Docker's published-port behavior for your host.

To operate and upgrade the deployment:

```bash
cd /opt/keycloak/caesar
docker compose ps
docker compose logs --tail 100 keycloak
docker compose restart keycloak
```

Do not run `docker compose down -v` on a live installation: it deletes the named PostgreSQL volume. Back up the database, review Keycloak and PostgreSQL release notes, and test migrations before updating image tags.


### 1.4 Create TLS certificates for Nginx

Keycloak is configured to serve HTTP on the local Docker port `127.0.0.1:8081`. To expose the authentication service securely, Nginx will terminate HTTPS connections on port `8443` and forward requests to the local Keycloak container.

The following example creates an internal Certificate Authority (CA) and a TLS server certificate. This approach is suitable for a controlled institutional deployment where administrators can distribute and manage the trusted CA certificate.

For public deployments, a certificate issued by an established trusted CA is generally preferable.

> **WARNING**: If your organization already operates a trusted CA, skip the CA creation procedure and obtain a server certificate through the approved certificate issuance process. Do not overwrite an existing CA certificate or private key.

#### Create the internal Certificate Authority

Create directories for the CA and the server certificates:

```bash
sudo install -d -m 0700 /etc/caesar-pki/ca
sudo install -d -m 0750 /etc/caesar-pki/keycloak
```

Generate the CA private key:

```bash
sudo openssl genpkey -algorithm RSA \
  -pkeyopt rsa_keygen_bits:4096 \
  -out /etc/caesar-pki/ca/ca.key

sudo chmod 0600 /etc/caesar-pki/ca/ca.key
```

Generate the self-signed CA certificate:

```bash
sudo openssl req -x509 -new \
  -key /etc/caesar-pki/ca/ca.key \
  -sha256 -days 3650 \
  -out /etc/caesar-pki/ca/ca.crt \
  -subj "/CN=CAESAR Internal CA/O=INAF" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
```

The example creates a CA certificate valid for approximately ten years. Choose the actual lifetime according to your organization's certificate policy.

**Security:** The CA private key is a highly sensitive signing credential. Ideally, generate and store it on a separate protected CA host, rather than on the application server. Only the public `ca.crt` certificate should be distributed to client systems.

#### Generate the Keycloak server certificate

Set the fully qualified domain name (FQDN) used by the Keycloak HTTPS endpoint. This must match the hostname configured in `KEYCLOAK_HOST` in Section 1.2, excluding the `https://` scheme and port number:

```bash
export KEYCLOAK_HOSTNAME="server.example.org"
```

The hostname must resolve to the Nginx server and must appear in the TLS certificate's Subject Alternative Name (SAN). If Keycloak and CAESAR-REST use the same hostname on different HTTPS ports, both Nginx virtual hosts may use the same TLS certificate.

Generate the server private key:

```bash
sudo openssl genpkey -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out /etc/caesar-pki/keycloak/keycloak.key

sudo chmod 0600 /etc/caesar-pki/keycloak/keycloak.key
```

Generate the Certificate Signing Request (CSR):

```bash
sudo openssl req -new \
  -key /etc/caesar-pki/keycloak/keycloak.key \
  -out /etc/caesar-pki/keycloak/keycloak.csr \
  -subj "/CN=${KEYCLOAK_HOSTNAME}/O=INAF" \
  -addext "subjectAltName=DNS:${KEYCLOAK_HOSTNAME}"
```

Create the certificate extensions file:

```bash
sudo tee /etc/caesar-pki/keycloak/server.ext >/dev/null <<EOF
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:${KEYCLOAK_HOSTNAME}
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EOF
```

Sign the CSR using the internal CA:

```bash
sudo openssl x509 -req \
  -in /etc/caesar-pki/keycloak/keycloak.csr \
  -CA /etc/caesar-pki/ca/ca.crt \
  -CAkey /etc/caesar-pki/ca/ca.key \
  -CAcreateserial \
  -out /etc/caesar-pki/keycloak/keycloak.crt \
  -days 365 -sha256 \
  -extfile /etc/caesar-pki/keycloak/server.ext
```

The signing operation should be performed on the protected CA host in production. The resulting public server certificate can then be installed on the Nginx host.

The example uses a one-year server certificate. Certificate renewal is documented in Section 3.

#### Verify the generated certificates

Inspect the certificate subject, issuer, expiration and Subject Alternative Name (SAN):

```bash
sudo openssl x509 \
  -in /etc/caesar-pki/keycloak/keycloak.crt \
  -noout -subject -issuer -dates -ext subjectAltName
```

Verify the server certificate against the internal CA:

```bash
sudo openssl verify \
  -CAfile /etc/caesar-pki/ca/ca.crt \
  -purpose sslserver \
  -verify_hostname "${KEYCLOAK_HOSTNAME}" \
  /etc/caesar-pki/keycloak/keycloak.crt
```

Expected output:

```text
/etc/caesar-pki/keycloak/keycloak.crt: OK
```

#### Install the internal CA certificate on trusted clients

Client machines must trust the internal CA to establish verified HTTPS connections to Keycloak.

On Ubuntu, install an independently verified copy of the public CA certificate:

```bash
sudo install -m 0644 caesar-internal-ca.crt \
  /usr/local/share/ca-certificates/caesar-internal-ca.crt

sudo update-ca-certificates
```

Here, `caesar-internal-ca.crt` is the trusted public certificate obtained from `/etc/caesar-pki/ca/ca.crt` through a secure distribution process.

This configuration may be required on CAESAR-REST servers, administrative workstations, API clients and other hosts accessing the Keycloak HTTPS endpoint.

Never distribute the CA private key or the server private key to client machines.

### 1.5 Configure Nginx as an HTTPS reverse proxy for Keycloak

Nginx provides the public HTTPS endpoint and forwards authenticated requests to the Keycloak Docker container.

The resulting network architecture is:

```text
Browser / API client
        |
        | HTTPS :8443
        v
      Nginx
        |
        | HTTP 127.0.0.1:8081
        v
  Keycloak container
        |
        | Docker internal network
        v
 PostgreSQL container
```

HTTPS terminates at Nginx. The HTTP connection to Keycloak remains restricted to the local Docker host.

#### Install Nginx

On Ubuntu:

```bash
sudo apt update
sudo apt install nginx
sudo systemctl enable --now nginx
```

Verify the installation:

```bash
sudo nginx -v
sudo systemctl status nginx
```

#### Configure the Keycloak reverse proxy

Create `/etc/nginx/sites-available/keycloak.conf`:

```nginx
server {
    listen 8443 ssl;
    server_name server.example.org;

    ssl_certificate /etc/caesar-pki/keycloak/keycloak.crt;
    ssl_certificate_key /etc/caesar-pki/keycloak/keycloak.key;

    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;

        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 8443;
        proxy_set_header X-Forwarded-Host $http_host;

        proxy_connect_timeout 30s;
        proxy_read_timeout 90s;
    }
}
```

Replace `server.example.org` with the actual FQDN `$KEYCLOAK_HOSTNAME` covered by the server certificate.

The forwarded headers allow Keycloak to reconstruct the external HTTPS URL correctly when generating redirects and processing browser authentication requests.

The upstream should remain bound to `127.0.0.1:8081`, as configured in the Docker Compose file. Do not expose the container's HTTP listener directly to external networks.

#### Enable the Nginx site

For an Ubuntu installation using `sites-available` and `sites-enabled`:

```bash
sudo ln -s /etc/nginx/sites-available/keycloak.conf \
  /etc/nginx/sites-enabled/keycloak.conf
```

If your Nginx installation uses `/etc/nginx/conf.d/` instead, place the configuration there and omit the symbolic link.

Verify the configuration:

```bash
sudo nginx -t
```

If the test succeeds, reload Nginx:

```bash
sudo systemctl reload nginx
```

Ensure that TCP port `8443` is reachable by authorized clients through the host or institutional firewall. The internal Keycloak port `8081` and PostgreSQL port `5432` should not be exposed publicly.

#### Verify Keycloak over HTTPS

First, verify the certificate chain:

```bash
openssl s_client \
  -connect "${KEYCLOAK_HOSTNAME}:8443" \
  -servername "${KEYCLOAK_HOSTNAME}" \
  -verify_return_error \
  </dev/null
```

When the issuing CA is trusted, the expected result is:

```text
Verify return code: 0 (ok)
```

Next, verify Keycloak's OpenID Connect discovery endpoint:

```bash
curl --fail-with-body -sS \
  "https://${KEYCLOAK_HOSTNAME}:8443/realms/master/.well-known/openid-configuration"  
```

This request should return a JSON document containing Keycloak's authorization, token, logout and other OIDC endpoints.

Check that the returned `issuer` uses the expected external HTTPS URL, rather than the internal Docker address.

If the internal CA is not yet installed in the local trust store, use its verified public certificate explicitly:

```bash
curl --cacert /etc/caesar-pki/ca/ca.crt \
  --fail-with-body -sS \
  "https://${KEYCLOAK_HOSTNAME}:8443/realms/master/.well-known/openid-configuration"  
```

Do not disable TLS verification to bypass certificate problems.

#### Access the Keycloak Administration Console

Open the following URL in a browser:

```text
https://server.example.org:8443/admin/
```

Sign in with the Keycloak bootstrap administrator credentials configured in the Docker Compose deployment.

Once the Keycloak Administration Console is accessible over HTTPS, proceed to Section 2 to configure the application realm, users and OIDC clients.

For production deployments, restrict access to the administration interface and the `master` realm according to the site's network and identity-management policies.


## 2. Configure Keycloak realm, users and OIDC clients

### Create the administrator, realm and users

After configuring the Nginx HTTPS virtual host (Section 1.5), open `https://server.example.org:8443/admin/`, replacing `server.example.org` with the actual Keycloak hostname. Sign in using the bootstrap administrator credentials and create a permanent administrative account according to your site's security policy.

Create the application realm in the Keycloak Admin Console:

1. Open the realm selector and select **Create realm**.
2. Set the realm name to **`caesar`**, enable it and save.
3. Select `caesar` before creating its clients or users. The `master` realm is reserved for server administration.
4. Under **Users**, select **Add user**, assign a username, enable the user, and save.
5. Under that user's **Credentials**, set an initial password and choose whether a password change is required on first login.
6. Assign groups or roles only as required by the CAESAR-REST authorization policy; creating a Keycloak user alone does not grant dataset administrator rights.

Create the `caesar-rest` and `insomnia-caesar` clients using the precise settings reported in the sections below. You can also create users through approved identity federation rather than local passwords.

### Confidential client: `caesar-rest`

In realm `caesar`, create or inspect the `caesar-rest` OpenID Connect client:

| Keycloak setting | Example value |
| --- | --- |
| Client authentication | ON (confidential client) |
| Standard Flow | ON |
| Client authorization | OFF |
| Other flows | OFF unless explicitly needed |
| Root URL | `https://CAESAR_REST_HOSTNAME:8444` |
| Home URL | `https://CAESAR_REST_HOSTNAME:8444/` |
| Valid redirect URI | `https://CAESAR_REST_HOSTNAME:8444/oidc_callback` |
| Web origins | `https://CAESAR_REST_HOSTNAME:8444` |

where `CAESAR_REST_HOSTNAME` is the hostname where `caesar-rest` web application is deployed (see [Web application deployment](web-application.md)).

After creating the confidential `caesar-rest` client, open **Clients** → **caesar-rest** → **Credentials** in the Keycloak Administration Console. Retrieve the generated client secret and store it securely in a deployment-specific OIDC client-secrets JSON file. The file format must be compatible with the installed `flask-oidc-ex` integration. Never commit the client secret or its configuration file to Git. See [Web application deployment](web-application.md) for the application-side OIDC configuration.

Some legacy deployments include `http://localhost` as a redirect URI for `caesar-rest` and `https://CAESAR_REST_HOSTNAME:8444/*` for post-logout redirection. Restrict these to exact necessary destinations for production; Insomnia should use its **own** client and callback instead of expanding the confidential client's allowed redirects.

### Public client: `insomnia-caesar`

| Keycloak setting | Example value |
| --- | --- |
| Client authentication | OFF (public client) |
| Standard Flow | ON |
| PKCE code challenge method | `S256` |
| Service accounts | OFF |
| Redirect URI | `http://localhost` for the tested Insomnia workflow |
| Scopes | `openid profile email` |

The callback must match the value actually used by the installed Insomnia version. Device Authorization Grant is **not required** for the successful Authorization Code + PKCE workflow.

### Configure Insomnia (Authorization Code + PKCE)

Create an HTTP request to `https://CAESAR_REST_HOSTNAME:8444/caesar/api/v1.0/apps` and open **Auth -> OAuth 2.0**. Set:

| Insomnia setting | Value |
| --- | --- |
| Grant type | Authorization Code |
| Authorization URL | `https://server.example.org:8443/realms/caesar/protocol/openid-connect/auth` |
| Access token URL | `https://server.example.org:8443/realms/caesar/protocol/openid-connect/token` |
| Client ID | `insomnia-caesar` |
| Client secret | Empty (public client) |
| Redirect URI | `http://localhost` for the documented Insomnia workflow; use the exact callback required by your installed version |
| Scope | `openid profile email` |
| PKCE | Enabled; SHA-256 / `S256` |

Register the identical redirect URI in **Clients -> insomnia-caesar -> Access settings -> Valid redirect URIs**. Use **Fetch Tokens**, authenticate through Keycloak, then ensure Insomnia sends the **access token** (not the ID token) as an `Authorization: Bearer` header. Complete the audience-mapper configuration below before expecting successful CAESAR-REST API introspection.

Older Insomnia versions may incorrectly send `code_challenge_method=undefined`; explicitly select the SHA-256 option. Insomnia 2023.3.0 was also observed to fail certificate validation in its OAuth authentication transport even when system `curl` worked. Disabling certificate validation can diagnose the problem, but **is not an acceptable permanent solution**. Update Insomnia or repair trust of the internal CA.

### Add the CAESAR-REST audience to API access tokens

Keycloak token introspection may return `"active": false` for an Insomnia token that did not identify `caesar-rest` as an intended audience. Configure the intended audience as follows:

1. In Keycloak, open **Clients -> insomnia-caesar -> Client scopes**.
2. Open **`insomnia-caesar-dedicated` -> Mappers -> Configure a new mapper -> Audience**.
3. Set **Included Client Audience** to `caesar-rest`.
4. Enable **Add to access token**, save, and obtain a **new** access token.

The token should have an `aud` claim including `caesar-rest`; `azp` identifies the client that requested the token (`insomnia-caesar`). Do not confuse the requesting client with the user whose identity is in `sub`. Verify the mapping by calling the protected CAESAR-REST `/apps` API with the newly issued access token.

Other clients, including external applications, require deliberate audience mappings if they request access tokens for CAESAR-REST.

### Configure CAESAR-REST to use Keycloak

After configuring the `caesar-rest` OIDC client, the CAESAR-REST application must be configured with the corresponding client credentials, Keycloak realm and authentication options.

The application must also trust the TLS certificate presented by the Keycloak HTTPS endpoint.

See [Web application deployment](web-application.md) for instructions on configuring and starting CAESAR-REST with OIDC authentication enabled.

## 3. Renew the existing internally signed server certificate

The following is an **example renewal procedure** for an internally signed certificate, reusing an existing server private key and the same internal CA. It assumes the administrator has verified that the CA certificate remains valid beyond the requested server-certificate end date, has access to the CA private key through approved procedures, and has arranged a protected backup. Longer-lived certificates increase risk and may not meet organizational policy; use the lifetime required by your PKI policy.

Before renewing the certificate, identify the fully qualified DNS hostname covered by the existing server certificate. The following example uses `server.example.org`. Certificate signing must be performed through an authorized CA process, preferably on a protected signing host rather than the public-facing Nginx server.

First inspect the existing certificates:

```bash
sudo openssl x509 -in /etc/caesar-pki/ca/ca.crt -noout -subject -issuer -dates
sudo openssl x509 -in /etc/caesar-pki/keycloak/keycloak.crt -noout -subject -issuer -dates -ext subjectAltName
```

Set `KEYCLOAK_HOSTNAME` to the DNS hostname of the certificate being renewed. This variable must be defined in the current shell, even if it was previously configured during the original installation.

```bash
export KEYCLOAK_HOSTNAME="server.example.org"
```

Replace `server.example.org` with the actual hostname before running the subsequent renewal commands.

Create a restricted working directory and extension file:

```bash
sudo install -d -m 0700 /etc/caesar-pki/renewal

sudo tee /etc/caesar-pki/renewal/server.ext >/dev/null <<EOF
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:${KEYCLOAK_HOSTNAME}
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EOF
```

Create a certificate-signing request with the existing server key, then sign using the existing internal CA (signing should occur in the organization's secure CA environment):

```bash
sudo openssl req -new \
  -key /etc/caesar-pki/keycloak/keycloak.key \
  -out /etc/caesar-pki/renewal/server.csr \
  -subj "/CN=${KEYCLOAK_HOSTNAME}/O=INAF"  

sudo openssl x509 -req \
  -in /etc/caesar-pki/renewal/server.csr \
  -CA /etc/caesar-pki/ca/ca.crt \
  -CAkey /etc/caesar-pki/ca/ca.key \
  -CAserial /etc/caesar-pki/ca/ca.srl \
  -CAcreateserial \
  -out /etc/caesar-pki/renewal/server.crt \
  -days 365 -sha256 \
  -extfile /etc/caesar-pki/renewal/server.ext
```

This example renews the server certificate for 365 days, matching the initial certificate issuance procedure in Section 1.4. Adjust the validity period according to your organization's PKI policy, ensuring that the issuing CA remains valid throughout the requested certificate lifetime.

Verify the new certificate and hostname before deployment:

```bash
sudo openssl verify \
  -CAfile /etc/caesar-pki/ca/ca.crt \
  -purpose sslserver \
  -verify_hostname "${KEYCLOAK_HOSTNAME}" \
  /etc/caesar-pki/renewal/server.crt  

sudo openssl x509 -in /etc/caesar-pki/renewal/server.crt \
  -noout -subject -issuer -dates -ext subjectAltName
```

Additionally compare the public key derived from the certificate with the public key derived from the existing private key, without printing the private key itself. 

```bash
sudo openssl x509 \
  -in /etc/caesar-pki/renewal/server.crt \
  -pubkey -noout |
  openssl pkey -pubin -outform DER |
  openssl dgst -sha256

sudo openssl pkey \
  -in /etc/caesar-pki/keycloak/keycloak.key \
  -pubout -outform DER |
  openssl dgst -sha256
```

The SHA-256 digests should match.

After successful verification, back up and replace **only the public server certificate**, then validate and reload Nginx:

```bash
BACKUP_DATE="$(date +%Y%m%d-%H%M%S)"

sudo cp -p /etc/caesar-pki/keycloak/keycloak.crt \
  "/etc/caesar-pki/keycloak/keycloak.crt.bak-${BACKUP_DATE}"
    
sudo install -m 644 /etc/caesar-pki/renewal/server.crt \
  /etc/caesar-pki/keycloak/keycloak.crt
sudo nginx -t && sudo systemctl reload nginx
```

Choose a unique timestamped backup filename for each renewal. Check the live certificate dates on **both** HTTPS ports and repeat browser/API authentication tests. Because the issuing CA and server key were preserved, existing client machines trusting that CA generally did not need a new certificate installed. **Do not** distribute the server private key as a substitute for the trusted CA certificate.

## 4. End-to-end verification

### Browser login

Open `https://server.example.org:8444/login` in a private browser window, replacing `server.example.org` with the actual CAESAR-REST hostname. Verify that the browser is redirected to Keycloak, the user can authenticate successfully, the authorization response is processed through `/oidc_callback`, and a valid browser session is established before returning to the CAESAR-REST application.

### Bearer-token API access

Obtain a short-lived access token with Authorization Code + PKCE, then issue a protected request:

```bash
export CAESAR_REST_HOSTNAME="server.example.org"

read -r -s -p 'Access token: ' ACCESS_TOKEN
printf '\n'

curl -i -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H 'Accept: application/json' \
  "https://${CAESAR_REST_HOSTNAME}:8444/caesar/api/v1.0/apps"

unset ACCESS_TOKEN
```

The working deployment returned **HTTP 200** and the list of applications. Calling the same protected endpoint without a bearer token should return **HTTP 401** when AAI is enabled. Do not paste access tokens, authorization codes or client secrets into logs or issue trackers.

### Introspection and identity

Keycloak introspection is available at:

```text
https://KEYCLOAK_HOSTNAME:8443/realms/caesar/protocol/openid-connect/token/introspect
```

A successfully introspected token for the API must be active and have an appropriate intended audience. Verified issuer (`iss`) and subject (`sub`) establish the dataset user's stable identity. Do not infer authorization merely because browser login succeeded: also test per-user dataset and job permissions.

## 5. Troubleshooting

| Symptom | Likely cause / recommended action |
| --- | --- |
| Clicking `/login` returned `invalid_token` | The browser route incorrectly required an API bearer token; use `custom_require_browser_login` rather than `custom_require_login` |
| `/oidc_callback` failed with `CERTIFICATE_VERIFY_FAILED` | `httplib2` used `certifi` rather than the trusted Ubuntu system CA bundle; set `HTTPLIB2_CA_CERTS` and verify HTTP 200 |
| Callback failed with `TypeError: cannot use a string pattern on a bytes-like object` | Legacy OIDC cookie serialization; corrected in the INAF fork, now installed at a pinned commit |
| Package initialization failed after later dependency upgrades | Older ItsDangerous serializer API removed; resolved by the fork's `URLSafeSerializer` update |
| Insomnia reported `code_challenge_method undefined` | PKCE method was not correctly sent; explicitly select SHA-256/S256 and obtain a new authorization request |
| Insomnia reported `failed to fetch token` | The observed case was tied to certificate validation in Insomnia's authentication transport; the insecure verification-off test worked, but is **not** a production solution |
| CAESAR-REST returned HTTP 401 with an Insomnia token | Keycloak introspection reported `active:false`; adding the `caesar-rest` audience to the `insomnia-caesar` client scope and obtaining a new token resolved it |

Some Insomnia versions may use certificate trust settings different from command-line `curl` and can fail OAuth token fetching even when `curl` succeeds. Keep certificate verification enabled for regular use and fix the client's trust settings or upgrade the client instead of relying on the diagnostic bypass.

## Operational and security checklist

- Verify Keycloak discovery and the two Nginx TLS virtual hosts; confirm expected external hostnames and ports.
- Keep the server key, CA signing key, OIDC client secret and Flask session secret outside Git; restrict permissions and plan rotation.
- Ensure the issuing CA is trusted by the browser, CAESAR-REST process, and external API clients as appropriate.
- Confirm `HTTPLIB2_CA_CERTS` is present in the running uWSGI service environment if needed.
- Keep Keycloak redirect URIs and web origins narrowly scoped; prefer Authorization Code + PKCE for public clients.
- Configure `caesar-rest` as an access-token audience for clients calling the CAESAR-REST API.
- Test browser login, bearer API authentication, HTTP 401 without a token, and cross-user dataset isolation separately.
- Re-check certificate expiration, backup/restore procedure, and client trust after TLS renewal.

## References

- [CAESAR-REST installation](../installation.md)
- [Web application deployment](web-application.md)
- [Keycloak guides](https://www.keycloak.org/guides)
- [Keycloak OIDC endpoints](https://www.keycloak.org/securing-apps/oidc-layers)
- [INAF flask-oidc-ex fork](https://github.com/inaf-oact-ai/flask-oidc-ex)

- [Keycloak production configuration](https://www.keycloak.org/server/configuration-production)
- [Keycloak database configuration](https://www.keycloak.org/server/db)
- [Keycloak reverse proxy](https://www.keycloak.org/server/reverseproxy)
- [Keycloak TLS configuration](https://www.keycloak.org/server/enabletls)
