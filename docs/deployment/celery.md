# Celery deployment (legacy)

> **Deprecated execution backend:** Celery support is retained primarily for historical compatibility and reference. It is no longer actively developed or maintained as a CAESAR-REST execution backend. **Slurm is the recommended backend** for new deployments.

This guide preserves the original Celery deployment architecture and operational examples from earlier CAESAR-REST versions. It documents the message broker, task-result backend, Celery workers and service management used by the legacy deployment.

Although the current CAESAR-REST codebase still contains Celery integration, the instructions below have not been validated against the current Python environment, Celery releases or Pipeline V2 architecture. They should not be treated as a supported production deployment procedure without additional compatibility testing.

For actively maintained deployment instructions, see [Slurm deployment](slurm.md), [Web application deployment](web-application.md) and [Deployment prerequisites](prerequisites.md).

## 1. Legacy architecture

The historical Celery deployment used three main components:

1. **Message broker:** RabbitMQ receives task messages submitted by the CAESAR-REST application and distributes them to Celery workers.
2. **Task-result backend:** Redis or MongoDB stores Celery task states and results.
3. **Celery workers:** One or more worker processes execute the scientific tasks received through the broker.

The CAESAR-REST application submits jobs through Celery when configured with `--job_scheduler=celery`.

The application also uses MongoDB for its own persistent data and job metadata. This should not be confused with the optional use of MongoDB as the Celery result backend.

Unlike the standalone job monitoring service used for Slurm and Kubernetes, legacy Celery jobs rely on Celery's task-state mechanisms.

The original deployment instructions are preserved below to document this architecture and facilitate the maintenance or migration of existing installations.

## 2. Message broker: RabbitMQ

The historical Celery deployment used RabbitMQ as its message broker. CAESAR-REST submitted tasks to the broker, and Celery workers consumed those tasks for execution.

On a Linux host where RabbitMQ is installed and managed by systemd, the service can be started with:

```bash
sudo systemctl start rabbitmq-server.service
sudo systemctl status rabbitmq-server.service
```

RabbitMQ user accounts, virtual hosts, permissions and network access must be configured separately. Avoid exposing an unauthenticated broker to untrusted networks.

The original deployment also referenced the historical Docker image [`sriggi/caesar-rest-broker:latest`](https://hub.docker.com/r/sriggi/caesar-rest-broker), with Docker Compose or Kubernetes configuration stored under the repository's `config/` directory. This image and its compatibility with current CAESAR-REST dependencies have not been revalidated. Treat it as an archival deployment reference rather than a recommended installation method.
   
## 3. Task-result backend: Redis or MongoDB

Celery requires a result backend when task states and execution results need to be stored and retrieved.

The historical CAESAR-REST deployment supported two result-backend configurations:

- **Redis:** A dedicated Redis service stores Celery task states and results.
- **MongoDB:** The existing MongoDB infrastructure may also be configured as the Celery result backend, independently of its role as CAESAR-REST's application database.

For a Redis installation managed by systemd, the service can be started with:

```bash
sudo systemctl start redis.service
sudo systemctl status redis.service
```

The actual service name may differ depending on the operating system and package installation.

The current CAESAR-REST application parser still recognizes `redis` and `mongodb` as Celery result-backend protocols through the `--result_backend_proto` option.

Configure credentials, network restrictions and persistent storage according to the selected backend. Do not expose Redis or MongoDB directly to untrusted networks.

The original documentation did not provide a validated Redis container image specifically for the CAESAR-REST Celery deployment.
   
## 4. Celery workers

Celery workers receive job tasks from the message broker and execute them using the CAESAR-REST task implementation.

The historical deployment launched workers with an explicitly configured broker URL, result backend, task queue and concurrency level.

For example:

```bash
celery \
	--broker="[BROKER_URL]" \
	--result-backend="[RESULT_BACKEND_URL]" \
	--app=caesar_rest \
	worker \
	--loglevel=INFO \
	--concurrency=2 \
	-Q celery
```

Replace the placeholders with the URLs corresponding to the broker and result backend configured for your deployment.

The `--concurrency` parameter controls the number of concurrent worker processes, while `-Q celery` selects the Celery task queue.

This command preserves the historical invocation pattern. Its compatibility with the currently installed Celery version, CAESAR-REST package and scientific execution containers must be verified before use.

### Application-side Celery configuration

The current application still accepts `--job_scheduler=celery` and retains options for configuring the broker and result backend.

Relevant options include:

| Option | Purpose |
| --- | --- |
| `--job_scheduler=celery` | Select the legacy Celery backend |
| `--broker_host` | Broker hostname |
| `--broker_port` | Broker port |
| `--broker_proto` | Broker connection protocol |
| `--broker_user` | Broker username |
| `--broker_pass` | Broker password |
| `--result_backend_host` | Result-backend hostname |
| `--result_backend_port` | Result-backend port |
| `--result_backend_proto` | Result-backend protocol, `redis` or `mongodb` |
| `--result_backend_user` | Result-backend username |
| `--result_backend_pass` | Result-backend password |
| `--result_backend_dbname` | Result-backend database identifier |

These options configure the legacy integration in `apps/run_app.py`. Their presence does not imply that the backend is covered by current deployment or Pipeline V2 compatibility tests.

See [Application CLI options](../reference/cli-options.md) for the general application configuration reference.
   
## 5. Historical systemd service configuration

The original deployment used the Celery `multi` command and a systemd service to supervise worker processes.

The following configuration is preserved as a historical reference. It reflects the Python environment and Celery process-management conventions used by older CAESAR-REST installations.

**Compatibility warning:** The example contains Python 2.7 paths and older Celery service-management conventions. These are not appropriate defaults for a current Python 3 deployment. Do not install the service unchanged without reviewing the Celery version, executable paths, worker initialization and service lifecycle.
  
### Worker environment configuration

Create `/etc/default/caesar-workers`. A historical example is also available under `config/celery/`.
   
```bash
# The names of the workers. Only one here. 
CELERYD_NODES="caesar_worker"    

# The name of the Celery App   
CELERY_APP="caesar_rest"
 
# Working dir    
CELERYD_CHDIR="/opt/caesar-rest"    

# Additional options    
CELERYD_OPTS="--time-limit=300 --concurrency=4"

# Log and PID directories    
CELERYD_LOG_FILE="/opt/caesar-rest/logs/%n%I.log"    
CELERYD_PID_FILE="/opt/caesar-rest/run/%n.pid"    

# Log level    
CELERYD_LOG_LEVEL=INFO    

# Path to celery binary, that is in your virtual environment    
CELERY_BIN=/usr/local/bin/celery    
```

### Worker systemd unit

Create `/etc/systemd/system/caesar-workers.service`:
   
```ini
[Unit]    
Description=Caesar Celery Worker Service    
After=network.target rabbitmq-server.target redis.target   

[Service]    
Type=forking   
User=caesar   
Group=caesar   
EnvironmentFile=/etc/default/caesar-workers
Environment="PATH=$INSTALL_DIR/bin"   
Environment="PYTHONPATH=$INSTALL_DIR/lib/python2.7/site-packages"   
WorkingDirectory=/opt/caesar-rest   
ExecStart=/bin/sh -c '${CELERY_BIN} multi start ${CELERYD_NODES} \    
  -A ${CELERY_APP} --pidfile=${CELERYD_PID_FILE} \   
  --logfile=${CELERYD_LOG_FILE} --loglevel=${CELERYD_LOG_LEVEL} ${CELERYD_OPTS}'    
ExecStop=/bin/sh -c '${CELERY_BIN} multi stopwait ${CELERYD_NODES} \    
  --pidfile=${CELERYD_PID_FILE}'   
ExecReload=/bin/sh -c '${CELERY_BIN} multi restart ${CELERYD_NODES} \   
  -A ${CELERY_APP} --pidfile=${CELERYD_PID_FILE} \   
  --logfile=${CELERYD_LOG_FILE} --loglevel=${CELERYD_LOG_LEVEL} ${CELERYD_OPTS}'    

[Install]    
WantedBy=multi-user.target   
```
  
### Starting the legacy worker service

Start the service with:
  
```bash
sudo systemctl start caesar-workers.service
```

The historical deployment also provided the Docker image [`sriggi/caesar-rest-worker:latest`](https://hub.docker.com/r/sriggi/caesar-rest-worker) , intended for Docker Compose or Kubernetes-based worker deployments. The corresponding historical configuration examples may be found under the repository's `config/` directory. The image and orchestration examples have not been validated against the current CAESAR-REST implementation and should be considered archival references.

## 6. Migration and maintenance considerations

Existing CAESAR-REST installations using Celery may require continued access to their historical configuration, broker services, result backend and worker environment.

Before maintaining or migrating such installations, review:

- The Python and Celery versions used by the original deployment.
- Broker and result-backend compatibility.
- Task definitions and the scientific application execution environment.
- Worker service configuration, credentials and filesystem permissions.
- Existing job metadata and any tasks still awaiting execution.

Celery support remains present in parts of the CAESAR-REST codebase, but it is not the recommended execution path for current scientific workloads.

For new installations and staged scientific pipelines, use the maintained [Slurm execution backend](slurm.md), together with the [job monitoring](job-monitoring.md) and [pipeline artifact retention](artifact-retention.md) services.

A migration from Celery to Slurm requires adapting job submission, scheduling configuration and worker execution arrangements. Existing queued or running Celery tasks should be handled according to the original deployment's operational procedures rather than assumed to transfer automatically.

## References

- [Deployment overview](index.md)
- [Deployment prerequisites](prerequisites.md)
- [Slurm deployment](slurm.md)
- [Application CLI options](../reference/cli-options.md)
- [Archived original README](../archive/ORIGINAL_README.md)
- [Celery documentation](https://docs.celeryq.dev/)
- [RabbitMQ documentation](https://www.rabbitmq.com/docs)
- [Redis documentation](https://redis.io/docs/latest/)

