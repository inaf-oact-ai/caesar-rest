# Installation

CAESAR-REST is a Python application backed by MongoDB and **one configured execution backend**. Slurm is the recommended backend; Kubernetes is an alternative, and Celery is legacy/deprecated. Backend-specific infrastructure (Slurm REST, Kubernetes, RabbitMQ, etc.) must be provisioned separately.

## Environment and Python dependencies

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

Install CAESAR-REST with the extras appropriate to your deployment. For actively developed Slurm installations with Keycloak/OIDC and uWSGI:

```bash
python -m pip install -e ".[slurm,auth,server]"
```

The convenience requirements file installs this same recommended profile:

```bash
python -m pip install -r requirements.txt
```

`pyproject.toml` is the authoritative Python dependency declaration; `requirements.txt` is a convenience entry point, not a separate dependency inventory. `setup.py` is retained only to install the repository's existing executable scripts and ancillary deployment files. No manual `PYTHONPATH` or `setup.py install` is required.

### Base dependencies

The base installation (`python -m pip install -e .`) includes Flask, MongoDB libraries, NumPy, Matplotlib, Astropy, Regions, PyYAML, `structlog`, `requests`, `python-dateutil` and other currently shared Python dependencies. These remain mandatory until their usage across the application has been isolated and tested. **Base-only installation is not a runnable scheduler deployment**: select and configure an execution backend.

### Select one job execution backend

| Backend | Python installation | Infrastructure | Status |
| --- | --- | --- | --- |
| **Slurm** | `python -m pip install -e ".[slurm]"` | Slurm cluster and Slurm REST daemon | **Recommended** |
| Kubernetes | `python -m pip install -e ".[kubernetes]"` | Kubernetes cluster and API access | Alternative; manifests need review |
| Celery | `python -m pip install -e ".[celery]"` | Celery workers, message broker and result backend | Legacy/deprecated |

The application and job monitor now default to `slurm`. Set `--job_scheduler` explicitly for other backends. Selecting a backend requires its corresponding Python extra and configured infrastructure. Startup should fail clearly when selected backend dependencies are missing; verify this behavior in a clean environment. See [deployment](deployment/index.md) and [CLI reference](reference/cli-options.md).

### Optional Python integrations

- **Authentication:** add `[auth]` for the INAF [`flask-oidc-ex`](https://github.com/inaf-oact-ai/flask-oidc-ex) fork; configure Keycloak, credentials and TLS trust separately. See [OIDC deployment](deployment/authentication.md).
- **Production WSGI server:** add `[server]` for uWSGI; Nginx is a separate system service. See [web application deployment](deployment/web-application.md).
- **Logging:** `structlog` remains a base dependency because it initializes the package logger. Filebeat is an optional external service, **not** a pip dependency; see [deployment prerequisites](deployment/prerequisites.md).
- **Scientific libraries:** currently part of base. Scientific applications themselves run in separately provisioned containers; see [container reference](reference/app-containers.md).

For an environment with all Python integration dependencies, use `python -m pip install -e ".[all]"`. This does not install the external services.

## Package installation and executable scripts

The commands above install the package as an **editable** checkout, convenient for development on `devel`. For a non-editable installation, omit `-e`:

```bash
python -m pip install ".[slurm,auth,server]"
```

The existing installed script names are preserved: `run_app.py`, `run_jobmonitor.py`, `run_artifact_retention.py`, and `run_accounter.py`. When the virtual environment is active, these are available on `PATH` from `.venv/bin/`.

No `python setup.py build`, `python setup.py sdist bdist_wheel`, or `python setup.py install` step is needed for a normal pip installation.

## Application containers

CAESAR-REST installs the REST service and its supporting Python code; **it does not install scientific application containers**. Scientific applications run in Docker/OCI containers for Kubernetes deployments or Singularity/Apptainer-compatible containers for Slurm deployments. The container images and the paths visible to the selected scheduler must be configured separately.

The [application containers reference](reference/app-containers.md) preserves the original README's container inventory, image names, `singularity pull` examples, cache and temporary directory settings, and troubleshooting notes. Review image versions and commands before using them in a production deployment.

## Required services and follow-up configuration

MongoDB is required to store user, job and pipeline information. The chosen scheduler requires its own infrastructure. Production deployments may additionally use Nginx/uWSGI, Keycloak/OIDC, and Filebeat. Multi-stage scientific pipelines require job monitoring and an artifact retention service with persistent storage.

Continue with the [deployment guides](deployment/index.md), [Slurm backend](deployment/slurm.md), and [pipeline artifact retention](deployment/artifact-retention.md).

### Verify the installed profile

After installation, verify dependency consistency and that the selected backend can be imported:

```bash
python -m pip check
python -m compileall -q caesar_rest apps
python - <<'PYTEST'
import caesar_rest
from caesar_rest.app import create_app
print("CAESAR-REST import OK", caesar_rest.__version__)
PYTEST
```

This is an import/compilation smoke test, **not** a substitute for configuring the scheduler, starting the REST service and job monitor, and submitting a test job. For installations with optional authentication, verify Keycloak/OIDC configuration and TLS trust separately.

## Compatibility and migration notes

The dependency groups separate the Python installation footprint. They do **not** by themselves validate each runtime profile; test imports, application startup, job monitoring and a scheduler job in clean environments before deploying. The Slurm client currently imports the `jwt` distribution's `JWT`/`jwa`/`jwk` interfaces; do not replace it with `PyJWT` without updating the client. Python version compatibility and a dependency lock remain to be established separately. The `[auth]` dependency tracks the GitHub `master` branch, so pinning a commit or release is advisable for reproducible production installations.
