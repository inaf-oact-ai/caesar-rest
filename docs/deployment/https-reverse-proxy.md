# HTTPS reverse proxy

> This page contains the original HTTPS/NGINX reverse proxy examples. Check hostname, TLS certificate and port configuration before applying them.

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 505–634). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

#### HTTPS reverse proxy configuration for CAESAR-REST and Keycloak

When OpenID Connect authentication is enabled, CAESAR-REST and Keycloak can be deployed behind an NGINX reverse proxy providing HTTPS termination.

The following configuration was tested with:

- CAESAR-REST exposed over HTTPS on port `8444`, using NGINX and uWSGI.
- Keycloak exposed over HTTPS on port `8443`, with NGINX forwarding requests to the internal Keycloak HTTP service on port `8081`.

Both services use TLS certificates configured in NGINX. Replace the hostnames, certificate paths, and uWSGI socket path with the values appropriate for the deployment.

**CAESAR-REST NGINX configuration**

```nginx
server {
    listen 8444 ssl;
    server_name [CAESAR_REST_HOST];

    ssl_certificate /etc/caesar-pki/keycloak/keycloak.crt;
    ssl_certificate_key /etc/caesar-pki/keycloak/keycloak.key;

    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 1000M;
    sendfile on;
    keepalive_timeout 0;

    location / {
        include uwsgi_params;

        # Tell Flask that the original request used HTTPS
        uwsgi_param HTTPS on;
        uwsgi_param UWSGI_SCHEME https;
        uwsgi_param HTTP_X_FORWARDED_PROTO https;
        uwsgi_param HTTP_X_FORWARDED_HOST $http_host;

        # Preserve the HTTPS host and port
        uwsgi_param HTTP_HOST $http_host;

        uwsgi_pass unix:[PATH_TO_SOCKET]/caesar-rest.sock;
    }
}
```

The `uwsgi_param` directives are particularly important when using OIDC authentication. They ensure that the Flask application receives the original HTTPS scheme, hostname, and port even though communication between NGINX and uWSGI takes place through a Unix socket.

This is necessary for generating correct external URLs, including the OIDC callback URL:

```text
https://[CAESAR_REST_HOST]:8444/oidc_callback
```

**Keycloak NGINX configuration**

```nginx
server {
    listen 8443 ssl;
    server_name [KEYCLOAK_HOST];

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

In this configuration, Keycloak runs internally over HTTP on `127.0.0.1:8081`, while NGINX exposes its public HTTPS endpoint.

The `X-Forwarded-*` headers preserve the original HTTPS request information, allowing Keycloak to generate the correct public URLs for authorization, token exchange, and redirects.

Keycloak must also be configured to recognize the external hostname and trusted proxy headers. The internal HTTP listener should not be directly exposed to external clients.

The public Keycloak issuer URL has the form:

```text
https://[KEYCLOAK_HOST]:8443/realms/caesar
```

This URL must match the issuer used in OIDC discovery and token validation.

**TLS certificates**

The example above uses the same certificate and private key files for the two NGINX virtual hosts. If different hostnames are used, the certificate must be valid for both names, or separate certificates should be configured.

The certificate chain must also be trusted by clients connecting to Keycloak and CAESAR-REST. Refer to the TLS certificate trust subsection below for additional configuration required by `httplib2`.

**Configuration verification**

After updating the NGINX configuration, validate it with:

```bash
sudo nginx -t
```

If the configuration is valid, reload NGINX:

```bash
sudo systemctl reload nginx
```

Verify the Keycloak discovery endpoint:

```bash
curl -i \
  https://[KEYCLOAK_HOST]:8443/realms/caesar/.well-known/openid-configuration
```

A successful response should contain the public issuer URL and the relevant OIDC endpoints.

Finally, verify that CAESAR-REST is accessible through HTTPS and that browser login redirects correctly to Keycloak and back to `/oidc_callback`.


