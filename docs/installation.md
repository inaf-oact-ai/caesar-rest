# Installation

CAESAR-REST is a Python REST service backed by MongoDB and **one configured job execution backend**. **Slurm is the recommended backend** for current deployments. Kubernetes is an alternative; Celery is a legacy/deprecated backend. The selected backend's external infrastructure must be provisioned separately.

This page covers Python installation and the available dependency profiles. Configuration and operation of services are described in the [deployment guides](deployment/index.md).

## Environment and Python dependencies

### Create a virtual environment

From the root of a CAESAR-REST source checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

Use a Python 3 interpreter compatible with your deployment. A complete supported-Python-version matrix has not yet been established; historical Python 3.6 commands are not an installation requirement.

### Install the recommended Slurm profile

For a Slurm deployment with Keycloak/OpenID Connect (OIDC) authentication and the uWSGI server:

```bash
python -m pip install -e ".[slurm,auth,server]"
```

Alternatively, the root `requirements.txt` installs that same recommended editable profile:

```bash
python -m pip install -r requirements.txt
```

**Choose one of these installation commands, not both.** `pyproject.toml` is the authoritative dependency definition. `requirements.txt` is a convenience entry point and does not independently list every Python package.

The installation requires Git when resolving the authentication extra, which retrieves the INAF-maintained `flask-oidc-ex` fork from GitHub at a pinned commit. Access to GitHub over HTTPS is therefore needed for a fresh `[auth]` installation.

### Core dependencies

A base installation (`python -m pip install -e .`) includes the shared libraries currently used by the REST service, including:

- **Web application:** Flask, Werkzeug, Jinja2 and MarkupSafe.
- **Database:** PyMongo and Flask-PyMongo.
- **General utilities:** PyYAML, `structlog`, `requests` and `python-dateutil`.
- **Scientific and supporting libraries:** NumPy, Matplotlib, Astropy, Regions and extension-helpers.

These are declared in `[project].dependencies` in `pyproject.toml`. They remain in the core set pending a separate import and compatibility audit.

The installed CAESAR-REST distribution also includes **two internal Python packages**, `caesar_rest` and `pipeline_runtime`. The latter implements shared Pipeline V2 execution, staging and integrity functionality; it is *not* an external pip dependency.

**A base-only installation does not provide an execution backend.** Install the corresponding backend extra and configure its infrastructure before running jobs.

### Choose a job execution backend

Exactly one backend must be selected for a deployment. The backend choice is separate from installing Python libraries.

| Backend | Python extra | Required external infrastructure | Project status |
| --- | --- | --- | --- |
| **Slurm** | `.[slurm]` | Slurm cluster, REST daemon and access credentials | **Recommended; actively developed** |
| Kubernetes | `.[kubernetes]` | Kubernetes cluster and API configuration | Alternative; deployment manifests need review |
| Celery | `.[celery]` | Celery workers, broker (for example RabbitMQ) and result backend | Legacy/deprecated |

For example, to install the Kubernetes backend instead of Slurm:

```bash
python -m pip install -e ".[kubernetes,auth]"
```

Or, for an explicitly selected legacy Celery deployment:

```bash
python -m pip install -e ".[celery,auth]"
```

Both the REST application and the standalone job monitor **default to `slurm`**. Set `--job_scheduler=kubernetes` or `--job_scheduler=celery` explicitly when selecting another backend; the selected backend must also have valid deployment configuration. See [Slurm](deployment/slurm.md), [Kubernetes](deployment/kubernetes.md), [Celery](deployment/celery.md) and the [CLI reference](reference/cli-options.md).

The Slurm profile does not require the Celery or Kubernetes Python libraries. Informational messages about unavailable optional backends can appear during module initialization; their absence is expected when those backends were not installed.

### Optional integrations and development tools

| Extra | What it installs | Notes |
| --- | --- | --- |
| `[auth]` | INAF `flask-oidc-ex` fork | Keycloak/OIDC configuration, credentials and TLS trust are separate; see [authentication](deployment/authentication.md) |
| `[server]` | uWSGI | Nginx is a separate system service; another compatible WSGI server may be used with its own configuration |
| `[dev]` | pytest | For automated test execution; not needed for a normal production installation |
| `[all]` | All declared optional integrations, including pytest | Useful for broad development checks; not a minimal production profile |

The OIDC fork is pinned in `pyproject.toml` to commit `af8653925150631b1b1d407839fc903c3b73814c`. This revision removes the obsolete documentation-theme Git submodule and replaces the legacy ItsDangerous serializer with the modern API. The fork's package version may remain unchanged across Git revisions; when upgrading an *already installed* environment, confirm that the pinned source revision was actually installed.

For a development environment with the recommended Slurm profile and pytest:

```bash
python -m pip install -e ".[slurm,auth,server,dev]"
```

**Logging:** `structlog` is a core Python dependency. Filebeat is optional external software for forwarding logs, not a pip extra. See [deployment prerequisites](deployment/prerequisites.md).

**Authentication:** the `[auth]` extra installs Python code only. A deployment using protected APIs or the dynamic dataset registry also requires correctly configured AAI/OIDC. See [authentication](deployment/authentication.md).

**External services:** pip does not install MongoDB, Slurm, Kubernetes, RabbitMQ, Nginx or Filebeat. Some Python packages, especially uWSGI and scientific dependencies, can additionally require system-level build tools or native libraries.

## Package installation and executable scripts

The `-e` option creates an **editable installation**, useful while developing against the `devel` branch. For a non-editable installation from the checkout, omit `-e`:

```bash
python -m pip install ".[slurm,auth,server]"
```

The small compatibility `setup.py` retains the existing installed executables and ancillary configuration files. The executables are available from the activated virtual environment (normally `.venv/bin/`):

- `run_app.py` — REST web application.
- `run_jobmonitor.py` — scheduler job monitoring.
- `run_artifact_retention.py` — Pipeline V2 artifact retention worker.
- `run_accounter.py` — accounting service.

No manual `PYTHONPATH`, custom installation prefix, `setup.py build`, `setup.py sdist bdist_wheel`, or `setup.py install` step is required for an ordinary pip installation.

## Application containers

Installing the CAESAR-REST Python package **does not install the scientific application containers**. Scientific applications execute in separately managed containers: typically Singularity/Apptainer-compatible containers on Slurm, and Docker/OCI images on Kubernetes. The scheduler must be configured with the appropriate image locations and accessible data, model, job and artifact storage paths.

The [application containers reference](reference/app-containers.md) preserves historical container names, image retrieval commands, cache and temporary-directory settings and troubleshooting notes. Verify container versions and commands before deploying them.

## Verify the installation

Check package consistency and import the core, pipeline and Slurm integration modules:

```bash
python -m pip check
python -m compileall -q caesar_rest pipeline_runtime apps
python - <<'PY'
import caesar_rest
import pipeline_runtime
from pipeline_runtime.integrity import validate_expected
from caesar_rest.app import create_app
from caesar_rest import jobmgr_slurm

assert jobmgr_slurm is not None, "Slurm backend is unavailable"
print("CAESAR-REST:", caesar_rest.__version__)
print("pipeline_runtime:", pipeline_runtime.__file__)
print("Core and Slurm imports OK")
PY
```

For a profile with authentication, additionally check OIDC initialization:

```bash
python - <<'PY'
from flask_oidc_ex import OpenIDConnect
from importlib.metadata import version

OpenIDConnect()
print("OIDC initialization OK; ItsDangerous:", version("itsdangerous"))
PY
```

If `[dev]` is installed, run the repository tests:

```bash
python -m pytest
```

These checks do not replace a functional deployment test. Verify the REST service, authenticated API requests, MongoDB connectivity and index initialization, job monitoring, a real scheduler submission and (for multi-stage workflows) retained artifact consumption. The recommended Slurm/OIDC/uWSGI profile has been confirmed to start successfully in a deployed environment, but this does not establish equivalent validation for the Kubernetes or Celery profiles.

## Required services and next steps

MongoDB is required for persisted application, user, job and pipeline information. One execution backend and its infrastructure must be configured. Production environments commonly use a WSGI server behind a reverse proxy and enable OIDC authentication. Multi-stage scientific workflows also require the job monitor and an artifact retention service with persistent storage.

Continue with the [deployment index](deployment/index.md), [Slurm deployment](deployment/slurm.md), [web application](deployment/web-application.md), [authentication](deployment/authentication.md) and [pipeline artifact retention](deployment/artifact-retention.md).

## Compatibility notes

- The Slurm client currently imports `JWT`, `jwa` and `jwk` from the `jwt` distribution. Do not replace that dependency with `PyJWT` without migrating and testing the client.
- The OIDC fork uses modern ItsDangerous serialization. Previously signed cookies or in-progress browser login states may no longer validate after the serializer migration; users may need to authenticate again.
- Python-version support and a reproducible lock or constraints file remain to be established. Dependency groups alone do not guarantee that every optional backend profile works in a clean environment.
- When updating the pinned OIDC fork commit, validate both package installation and actual authentication behavior. A normal pip command may retain an already installed fork distribution when its declared version has not changed.
