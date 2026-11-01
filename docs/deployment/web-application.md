# Web application in production

CAESAR-REST can be deployed behind Nginx using uWSGI and a Unix-domain socket. Nginx provides the public HTTPS endpoint, while uWSGI serves the Flask application locally. This guide also explains how to enable Keycloak/OpenID Connect (OIDC) authentication and configure the Python TLS trust required for communication with the identity provider.

The paths, hostnames, service names and ports below are **deployment examples**. Substitute your actual values and verify the WSGI entry point and application startup options against the installed CAESAR-REST version. The repository's older `config/uwsgi/` examples are retained as historical references; in particular, do not copy their Python 2.7 paths into a current deployment. For Keycloak installation, TLS certificate issuance, realm and OIDC client setup, see [Keycloak and OpenID Connect authentication](authentication.md).

## 1. Install the application and prepare its runtime

Install CAESAR-REST in a dedicated Python environment according to the [installation guide](../installation.md). For a uWSGI deployment that uses Slurm and Keycloak authentication, install the corresponding optional dependencies from the repository root:

```bash
python -m pip install -e '.[slurm,auth,server]'
python -m pip check
```

The `auth` extra installs the INAF `flask-oidc-ex` fork at the revision pinned in `pyproject.toml`; the `server` extra installs uWSGI. Add or replace optional extras to match your chosen job backend. Use a consistent interpreter and environment for installation and service startup.

Prepare a runtime directory for the uWSGI socket and ensure that the application service account can create the socket there. The Nginx worker must be able to access the socket. For example, if CAESAR-REST runs as `caesar` and Nginx runs as group `www-data`, the runtime directory, socket ownership and modes must be configured accordingly. Avoid exposing the application's internal uWSGI socket as a public HTTP listener.

## 2. Run CAESAR-REST with uWSGI

The recommended deployment uses a Bash launcher (`launch_app.sh`) to configure CAESAR-REST and start uWSGI. The following example illustrates the essential settings; adapt the paths and application options to your installation.

```bash
#!/bin/bash
set -e

# - Python environment
VENV="/opt/caesar-rest/venv"
UWSGI_EXE="$VENV/bin/uwsgi"
FILE="$VENV/bin/run_app.py"

# - uWSGI settings
UWSGI_SOCKET="/opt/caesar-rest/run/caesar-rest.sock"
NWORKERS=1
NTHREADS=1
SOCKET_TIMEOUT=65

# - CAESAR-REST application settings
PYARGS="--db --dbhost=127.0.0.1 --dbname=caesardb --dbport=27017"
PYARGS="$PYARGS --datadir=/opt/caesar-rest/data"
PYARGS="$PYARGS --jobdir=/opt/caesar-rest/jobs"
PYARGS="$PYARGS --modeldir=/opt/caesar-rest/models"

# - Prepare the socket directory
mkdir -p "$(dirname "$UWSGI_SOCKET")"

# - Start uWSGI
exec "$UWSGI_EXE" \
	--wsgi-file="$FILE" \
	--callable=app \
	--pyargv="$PYARGS" \
	--workers="$NWORKERS" \
	--enable-threads \
	--threads="$NTHREADS" \
	--socket="$UWSGI_SOCKET" \
	--socket-timeout="$SOCKET_TIMEOUT" \
	--master \
	--chmod-socket=666 \
	--buffer-size=32768 \
	--vacuum \
	--die-on-term
```

The `FILE` variable identifies the installed CAESAR-REST WSGI entry point (`run_app.py`). Its location depends on the Python environment and installation method.

The `PYARGS` variable contains command-line options intended for CAESAR-REST, rather than uWSGI. The launcher passes these options to the Python application through `--pyargv="$PYARGS"`. This example assumes whitespace-separated options without embedded spaces; more complex argument values require additional handling.

The launcher uses `exec` to replace the Bash process with uWSGI, allowing systemd to supervise the server directly.

The Unix socket must match the Nginx `uwsgi_pass` directive in Section 4. Its parent directory must exist, and its ownership and permissions must allow the Nginx worker to connect. The example uses socket mode `666`, matching the tested deployment; for shared production hosts, prefer `660` with appropriate group permissions and restricted directory access.

### Run uWSGI as a systemd service

The following example defines `/etc/systemd/system/caesar-rest.service` to start the CAESAR-REST application through `launch_app.sh`. Replace `/opt/caesar-rest` with the actual deployment directory, ensure that the launcher is executable, and configure the launcher with the correct uWSGI executable, WSGI entry point, application arguments and socket settings. The socket directory must exist and have suitable permissions before the service starts.

```ini
[Unit]
Description=CAESAR-REST web application
After=network.target mongod.service caesar-rest-jobmonitor.service
ConditionPathExists=/opt/caesar-rest/launch_app.sh

[Service]
Type=simple
User=caesar
Group=caesar
WorkingDirectory=/opt/caesar-rest
ExecStart=/opt/caesar-rest/launch_app.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The systemd service runs `launch_app.sh` as the `caesar` user. The launcher prepares the application arguments and starts uWSGI directly. The `ExecStart` and `ConditionPathExists` paths must reference the same executable script. The `After=` directive establishes startup ordering but does not guarantee that dependent services are ready. Adjust the service dependencies and restart policy to your deployment.

After installing or modifying the service file:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now caesar-rest.service
sudo systemctl status caesar-rest.service
sudo journalctl -u caesar-rest.service -n 100 --no-pager
```

Use `sudo systemctl restart caesar-rest.service` after subsequent runtime configuration changes. A custom Nginx systemd unit is normally unnecessary when Nginx is installed from supported distribution packages.

## 3. Enable Keycloak/OIDC authentication

Keycloak is configured separately in the [authentication](authentication.md) guide, which covers the `caesar` realm, the confidential `caesar-rest` client, and client redirects. To enable authentication, add the following statements to `launch_app.sh` **after the existing** `PYARGS` **assignments and before the** `exec` **command that starts uWSGI**:

```bash
# Add authentication options to the launcher
PYARGS="$PYARGS --aai"
PYARGS="$PYARGS --secretfile=/SECURE/PATH/client_secrets.json"
PYARGS="$PYARGS --openid_realm=caesar"
```

The `--aai` option enables application authentication. The client-secrets JSON file must contain the credentials and provider settings required by the installed `flask-oidc-ex` integration. Use the generated secret of the **confidential** Keycloak client named `caesar-rest`, not the public Insomnia test client. Restrict file permissions to the application account and do not commit the file, access tokens or client secrets to Git.

With authentication enabled, browser login redirects to Keycloak and returns through `/oidc_callback`. Protected REST API requests must provide an OAuth access token through `Authorization: Bearer ...`; they should not rely on browser-session redirection. A user's successful authentication does not in itself grant access to another user's datasets or jobs.

**Session security:** Configure Flask with a strong, persistent deployment-specific `SECRET_KEY`. Do not use a hardcoded or ephemeral default. Deploy over HTTPS and review secure session-cookie settings for your environment.

## 4. Configure HTTPS with Nginx

Nginx terminates HTTPS on the CAESAR-REST endpoint (example port `8444`) and passes requests to the local uWSGI socket. In the example Keycloak installation, the authentication service uses port `8443` on the same hostname. The same TLS certificate may be used for both virtual hosts when its Subject Alternative Name (SAN) covers that hostname; the port is not part of certificate hostname matching. If the services use different names, supply certificates covering the corresponding DNS names.

Create `/etc/nginx/sites-available/caesar-rest.conf`, replacing `server.example.org`, the certificate paths if necessary, and the uWSGI socket path:

```nginx
server {
    listen 8444 ssl;
    server_name server.example.org;

    ssl_certificate /etc/caesar-pki/keycloak/keycloak.crt;
    ssl_certificate_key /etc/caesar-pki/keycloak/keycloak.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 1000M;
    sendfile on;
    keepalive_timeout 0;

    location / {
        include uwsgi_params;
        uwsgi_param HTTPS on;
        uwsgi_param UWSGI_SCHEME https;
        uwsgi_param HTTP_X_FORWARDED_PROTO https;
        uwsgi_param HTTP_X_FORWARDED_HOST $http_host;
        uwsgi_param HTTP_HOST $http_host;

        uwsgi_pass unix:/opt/caesar-rest/run/caesar-rest.sock;
    }
}
```

The HTTPS-related uWSGI parameters were used in the working reverse-proxy configuration to expose the correct external scheme and host to Flask/OIDC. Ensure that the Nginx worker can access the socket without granting unnecessary filesystem permissions. The TLS certificate and private key are installed on the Nginx host; client systems must trust the issuing CA as applicable.

On Ubuntu with `sites-available` / `sites-enabled`:

```bash
sudo ln -s /etc/nginx/sites-available/caesar-rest.conf \
  /etc/nginx/sites-enabled/caesar-rest.conf
sudo nginx -t
sudo systemctl reload nginx
```

If your distribution uses `/etc/nginx/conf.d/`, use that configuration mechanism instead. Open TCP port `8444` only to the intended clients. The application should then be reachable at `https://server.example.org:8444/` (using your actual hostname).

**Alternative topologies:** The legacy guide also illustrated Nginx forwarding to multiple backends and containerized deployments. Those are possible alternatives, but they require topology-specific socket/proxy configuration, TLS handling and security review; the single-host uWSGI example above does not validate them.

## 5. Configure Python TLS trust for OIDC

CAESAR-REST communicates with Keycloak over HTTPS to obtain OIDC metadata and perform authentication-related requests. When Keycloak uses an internal CA, install the independently verified public CA certificate into the trust store on the CAESAR-REST host as described in [the authentication guide](authentication.md). Never distribute the CA signing key or the server private key to application clients.

### Configure the `httplib2` CA bundle

The CAESAR-REST OIDC dependency stack includes `flask-oidc-ex`, `oauth2client` and `httplib2`. In an observed deployment using `httplib2` 0.22.0, Python selected the `certifi` certificate bundle rather than the Ubuntu system CA bundle, resulting in `SSLCertVerificationError: unable to get local issuer certificate` even though system OpenSSL and `curl` worked.

When this issue affects the installed Python environment, point `httplib2` to the system CA bundle:

```bash
# Use the system CA bundle, including the trusted internal CA
export REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"
export SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"
export HTTPLIB2_CA_CERTS="/etc/ssl/certs/ca-certificates.crt"
```

These variables configure certificate trust for Python HTTPS clients, including `requests`, OpenSSL-based clients and `httplib2`. When using the Bash launcher described in Section 2, place these exports in `launch_app.sh` before the command that starts uWSGI. The system CA bundle must already contain the trusted internal CA certificate, as explained in the [Keycloak authentication](authentication.md) guide.

Test from the **same Python environment** used by the running application, substituting the actual Keycloak hostname. Before running this test in an interactive shell, export the certificate environment variables shown above; variables configured only in launch_app.sh or systemd are not automatically inherited by your interactive shell:

```bash
export KEYCLOAK_HOSTNAME="server.example.org"
python - <<'PY'
import os
import httplib2

url = f"https://{os.environ['KEYCLOAK_HOSTNAME']}:8443/realms/caesar/.well-known/openid-configuration"
response, _ = httplib2.Http().request(url)
print('CA bundle:', httplib2.CA_CERTS)
print('HTTP status:', response.status)
PY
```

The expected result is HTTP `200`. A successful command-line test does not establish that the same environment variables are present inside a systemd-managed service.

### Persist Python TLS trust in the application service

The certificate environment variables must be available to the CAESAR-REST Python process before the OIDC libraries are initialized.

For the launcher-based deployment described in Section 2, the recommended approach is to export these variables directly in `launch_app.sh`, before executing uWSGI. Since the launcher is executed by systemd, the environment variables are inherited by the uWSGI process and its Python application.

Alternatively, the same settings can be configured directly in the systemd service or a systemd drop-in:

```ini
[Service]
Environment="REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt"
Environment="SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt"
Environment="HTTPLIB2_CA_CERTS=/etc/ssl/certs/ca-certificates.crt"
```

Only one configuration approach is necessary. There is no need to define the same environment variables in both the launcher and the systemd unit.

After modifying `launch_app.sh`, restart the application service:

```bash
sudo systemctl restart caesar-rest.service
```

If you modify the systemd unit or a drop-in instead, first reload the systemd configuration:

```bash
sudo systemctl daemon-reload
sudo systemctl restart caesar-rest.service
```

Never disable TLS certificate verification as a production workaround. Install the correct trusted CA certificate and ensure the Python process uses the appropriate CA bundle.

## 6. Verify the deployed web application

1. Confirm that `sudo nginx -t` passes, the uWSGI service is active, and Nginx can connect to the Unix socket.
2. Verify that the running uWSGI process received the expected application arguments, particularly `--aai`, `--secretfile` and `--openid_realm`, when authentication is enabled. Check the application startup logs without exposing client secrets or access tokens.
3. Visit `https://server.example.org:8444/`, substituting the actual CAESAR-REST hostname, and verify the server certificate and page load.
4. With `--aai` enabled, test browser login through Keycloak and the `/oidc_callback` return route.
5. Obtain an access token using an authorized Keycloak client and call a protected API endpoint with `Authorization: Bearer ...`; verify that a request without a token is rejected.
6. Confirm that users cannot access datasets or jobs owned by other users without authorization. See [authentication end-to-end verification](authentication.md#4-end-to-end-verification) for more detail.

## References

- [CAESAR-REST installation](../installation.md)
- [Keycloak and OpenID Connect authentication](authentication.md)
- [uWSGI configuration example](https://github.com/inaf-oact-ai/caesar-rest/blob/devel/config/uwsgi/uwsgi.ini)
- [Original README deployment instructions](../archive/ORIGINAL_README.md)
