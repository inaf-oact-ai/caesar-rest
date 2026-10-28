# Installation

This guide describes how to prepare a Python environment, install CAESAR-REST dependencies, and install the package. Service configuration and startup instructions are covered in the [deployment guides](deployment/index.md).

CAESAR-REST requires **one configured job execution backend**. **Slurm is the recommended backend** for current deployments. Kubernetes remains an alternative, while Celery is a legacy/deprecated option.

## Environment and dependencies

### Create a Python virtual environment

From the root directory of a CAESAR-REST source checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

Use a Python 3 version compatible with the target deployment and its dependencies. The current repository has not yet established an authoritative supported-version matrix; do not interpret historical Python 3.6 examples as a requirement.

### Install Python dependencies

```bash
python -m pip install -r requirements.txt
```

The repository's `requirements.txt` includes, among others:

- **Web/API:** Flask, Werkzeug, Jinja2, uWSGI.
- **Persistence:** PyMongo and Flask-PyMongo.
- **Scientific and supporting libraries:** NumPy, Matplotlib, Astropy, Regions, PyYAML, Structlog and other utilities.
- **Authentication:** the INAF-maintained [`flask-oidc-ex` fork](https://github.com/inaf-oact-ai/flask-oidc-ex), installed from its GitHub `master` branch.
- **Job backends:** Requests and `jwt` for Slurm integration, the Kubernetes Python client, and `celery<5.0.0` for the legacy Celery backend.

**Important:** This command installs Python packages only. External services and system libraries must be provisioned separately. Some Python dependencies, particularly uWSGI and scientific libraries, may require system build tools or native libraries depending on the platform.

The current requirements file includes libraries for **all three** execution backends, even though only one backend needs to be selected at deployment time.

### Required services

#### MongoDB

A [MongoDB](https://www.mongodb.com/) service stores application, user, job and pipeline information. It must be accessible to the REST service and relevant background workers. See [deployment prerequisites](deployment/prerequisites.md).

#### Job execution backend — choose one

| Backend | Project status | Additional infrastructure |
| --- | --- | --- |
| **Slurm** | **Recommended; actively developed** | Slurm cluster and Slurm REST daemon, configured for authenticated API access. See [Slurm deployment](deployment/slurm.md). |
| Kubernetes | Alternative; deployment manifests require review | Kubernetes cluster and API credentials/configuration. See [Kubernetes deployment](deployment/kubernetes.md). |
| Celery | Legacy/deprecated; not actively maintained | Celery workers, a message broker (e.g. RabbitMQ) and a result backend (e.g. Redis or MongoDB). See [Celery deployment](deployment/celery.md). |

The selected backend is configured when starting CAESAR-REST, using the `--job_scheduler` option (for example, `--job_scheduler=slurm`). **The code currently defaults to `celery` if this option is omitted**, so Slurm installations should select Slurm explicitly. See the [CLI reference](reference/cli-options.md).

### Web serving and reverse proxy

For production deployments, CAESAR-REST can run behind [uWSGI](https://uwsgi-docs.readthedocs.io/) and [Nginx](https://nginx.org/) (or an alternative supported WSGI/reverse-proxy arrangement). These components are not all installed by pip: Nginx is an external service, whereas uWSGI is listed as a Python dependency.

See [web application deployment](deployment/web-application.md) and [HTTPS reverse proxy configuration](deployment/https-reverse-proxy.md).

### Authentication (optional deployment configuration)

CAESAR-REST supports Keycloak/OpenID Connect authentication through the [`flask-oidc-ex` fork](https://github.com/inaf-oact-ai/flask-oidc-ex). Its Python dependency is already declared in `requirements.txt`; enabling authentication additionally requires a configured identity provider, client credentials, TLS trust and the corresponding application options.

See [Keycloak/OIDC deployment](deployment/authentication.md).

### Log forwarding (optional)

[Filebeat](https://www.elastic.co/guide/en/beats/filebeat/index.html) may be installed and configured separately to forward service logs to an Elastic/Logstash stack. It is not a Python package installed by `requirements.txt`. See [deployment prerequisites](deployment/prerequisites.md).

## Package installation

With the virtual environment activated and from the repository root, install CAESAR-REST itself:

```bash
python -m pip install -e .
```

This **editable installation** is recommended when working with a source checkout on the actively developed `devel` branch. For a non-editable installation, use:

```bash
python -m pip install .
```

The package's `setup.py` declares the CAESAR-REST package, Python requirements, and executable scripts including:

- `run_app.py` — REST web application.
- `run_jobmonitor.py` — job monitoring service.
- `run_artifact_retention.py` — pipeline artifact retention worker.
- `run_accounter.py` — accounting service.

The executables are installed into the active virtual environment, normally under `.venv/bin/`. No manual `PYTHONPATH`, `PATH`, `setup.py build`, or `setup.py install --prefix=...` commands are necessary.

> **Dependency note:** `setup.py` also declares installation requirements. Installing the package can therefore cause pip to resolve or update dependencies in addition to those installed using `requirements.txt`. Both declarations should be kept consistent as the project evolves.

## Application containers

Scientific applications run in containers: Docker/OCI images in Kubernetes deployments and Singularity/Apptainer-compatible containers in Slurm deployments. Images and execution paths must be configured for the chosen backend.

The original README's container inventory, Docker Hub image names, `singularity pull` instructions, cache/temp directory variables, and session-directory size troubleshooting notes are preserved in [application containers reference](reference/app-containers.md).

## Next steps

After installing the Python package, follow the [deployment and services guide](deployment/index.md) to configure MongoDB, the selected execution backend, web serving, job monitoring, and (for multi-stage pipelines) artifact retention.

For the detailed application command-line switches, consult [CLI options](reference/cli-options.md).

