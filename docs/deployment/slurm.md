# Slurm deployment

Slurm is the **recommended execution backend** for CAESAR-REST. This guide covers the Slurm cluster services, JWT-enabled `slurmrestd`, and the configuration needed for CAESAR-REST job submission, monitoring, and Pipeline V2 execution.

CAESAR-REST currently uses **Slurm REST API `v0.0.36`**. The controller API and the accounting API must both be exposed by `slurmrestd` to support recovery of completed job statuses. The examples below follow the project's existing deployment and historical cluster notes; adapt package names, unit paths, users, partition names, and Slurm configuration to the installed version and distribution.

A working Slurm deployment needs:

- A Slurm controller (`slurmctld`) and compute daemon(s) (`slurmd`), plus Munge authentication and consistent cluster identities.
- SlurmDBD (`slurmdbd`) with a configured accounting database (typically MariaDB/MySQL). This is **required for the job-accounting recovery described below**.
- The Slurm REST daemon (`slurmrestd`), built/installed with JWT authentication support and the **controller and database OpenAPI plugins**.
- A Slurm user authorized to submit and inspect jobs, a JWT signing arrangement, and network access between CAESAR-REST and `slurmrestd`.
- Shared or mapped job, data, model, and (for staged pipelines) retained-artifact paths visible where execution occurs. Scientific container images must be available to the compute nodes.

The Python application is installed separately using the [`slurm` optional dependency group](../installation.md), usually together with `auth` and `server`. MongoDB stores CAESAR-REST job and pipeline metadata; **it is not a substitute for SlurmDBD**.

In this section we provide some guidance on how to set up a Slurm cluster, including creation of the `munge` and `slurm` users, installing Munge, creating a shared Munge key, provisioning MariaDB, creating Slurm's accounting database, and configuring the controller and compute nodes. Those steps are cluster-administration tasks and depend on OS and Slurm release, so double-check them against the official Slurm documentation.

After completing the configuration, try these verification commands on appropriate cluster hosts:

```bash
systemctl status munge slurmctld slurmdbd slurmrestd
systemctl status slurmd
munge -n | unmunge
sinfo
scontrol ping
sacctmgr list cluster
```

Not every daemon runs on the same node. In particular, `slurmd` runs on compute nodes, and the SlurmDBD service and REST daemon may be on different machines. 

## Slurm pre-installation steps

### Install and configure Munge  

#### Create munge/slurm users

Slurm and Munge require consistent UID and GID across every node in the cluster. For all the nodes, before you install Slurm or Munge:

```bash
export MUNGEUSER=1005
groupadd -g $MUNGEUSER munge
useradd  -m -c "MUNGE Uid 'N' Gid Emporium" -d /var/lib/munge -u $MUNGEUSER -g munge  -s /sbin/nologin munge
export SlurmUSER=1001
groupadd -g $SlurmUSER slurm
useradd  -m -c "Slurm workload manager" -d /var/lib/slurm -u $SlurmUSER -g slurm  -s /bin/bash slurm
```

#### Install Munge for authentication

CentOS

```bash
yum install munge munge-libs munge-devel -y
```

Ubuntu

```bash
sudo apt install munge libmunge2 libmunge-dev
```

#### Create Munge authentication key  

If you don't see a key at `/etc/munge/munge.key`, you should create one manually by running the following command:

```bash
/usr/sbin/create-munge-key
```

#### Set user rights  

CentOS

```bash
chown -R munge: /etc/munge/ /var/log/munge/ /var/lib/munge/ /run/munge/
chmod 0700 /etc/munge/ /var/log/munge/ /var/lib/munge/ /run/munge/
cexec chown -R munge: /etc/munge/ /var/log/munge/ /var/lib/munge/ /run/munge/
cexec chmod 0700 /etc/munge/ /var/log/munge/ /var/lib/munge/ /run/munge/
```

Ubuntu

```bash
sudo chown -R munge: /etc/munge/ /var/log/munge/ /var/lib/munge/ /run/munge/
sudo chmod 0700 /etc/munge/ /var/log/munge/ /var/lib/munge/
sudo chmod 0755 /run/munge/
sudo chmod 0700 /etc/munge/munge.key
sudo chown -R munge: /etc/munge/munge.key
```

#### Enable and Start the munge service  

```bash
sudo systemctl daemon-reload
sudo systemctl enable munge
sudo systemctl restart munge
```

#### Test the installation  

```bash
munge -n | unmunge
```

You should see something like STATUS: SUCCESS. 

### Install and configure MariaDB 

#### Install mariadb

CentOS
```bash
yum install mariadb-server -y
```

Ubuntu
```bash
apt install mariadb-server -y
```

#### Activate and start the mariadb service 

```bash
systemctl enable mariadb
systemctl start mariadb
```

#### Secure mariadb installation 

```bash
mysql_secure_installation
```

#### Modify the innodb configuration 

Setting innodb_lock_wait_timeout,innodb_log_file_size and innodb_buffer_pool_size to larger values than the default is recommended.
To do that, create the file /etc/my.cnf.d/innodb.cnf (Ubuntu: /etc/mysql/conf.d/innodb.cnf) with the following lines:

```ini
[mysqld]
 innodb_buffer_pool_size=1024M
 innodb_log_file_size=64M
 innodb_lock_wait_timeout=900
``` 
 
To implement this change you have to shut down the database and move/remove logfiles:

```bash
systemctl stop mariadb
mv /var/lib/mysql/ib_logfile? /tmp/
systemctl start mariadb
```

> **Warning**: The InnoDB settings shown above are illustrative and should be adjusted to the installed MariaDB version and expected accounting workload. Consult the corresponding MariaDB documentation before changing redo-log parameters. Do not manually remove or relocate InnoDB redo-log files as part of routine configuration changes.

### Create JWT auth key

Create a JWT HMAC key at `/var/spool/slurmctld/jwt_hs256.key`:   

```bash
sudo dd if=/dev/random of=/var/spool/slurmctld/jwt_hs256.key bs=32 count=1
sudo chown slurm:slurm /var/spool/slurmctld/jwt_hs256.key
sudo chmod 0600 /var/spool/slurmctld/jwt_hs256.key
```

This will be used by both `slurmctld` and `slurmdbd` services. The `AuthAltParameters` configuration parameter (see below) is used to identify the key path. 

> **Security warning**: The JWT HMAC signing key is highly sensitive. Anyone possessing it may be able to generate valid Slurm authentication tokens for different user identities. CAESAR-REST currently generates JWTs using key material supplied through --slurm_keyfile. Access to this key must therefore be restricted to explicitly trusted processes and administrators. Never commit the signing key to a repository or expose it in logs. For production deployments, consider a dedicated token-issuing service to avoid distributing the signing key.

See the [official Slurm JWT guide](https://slurm.schedmd.com/jwt.html) for more details.


## Slurm installation

#### Install slurm  

Ubuntu: 

```bash
sudo apt install slurm-wlm slurmctld slurmdbd slurmrestd
```

#### Configure slurm   

Set options in `/etc/slurm/slurm.conf` configuration file:  

```ini 
ClusterName=[CLUSTNAME]
SlurmUser=[USER]
SlurmctldHost=[HOSTNAME]     
SlurmctldPort=6817
SlurmdPort=6818
AuthType=auth/munge
AuthAltTypes=auth/jwt
AuthAltParameters=jwt_key=/var/spool/slurmctld/jwt_hs256.key
StateSaveLocation=/var/spool/slurmctld
SlurmdSpoolDir=/var/spool/slurmd

SwitchType=switch/none
MpiDefault=none
SlurmctldPidFile=/var/run/slurmctld.pid
SlurmdPidFile=/var/run/slurmd.pid
ProctrackType=proctrack/pgid
ReturnToService=0

# TIMERS
SlurmctldTimeout=300
SlurmdTimeout=300
InactiveLimit=0
MinJobAge=300
KillWait=30
Waittime=0

# SCHEDULING
SchedulerType=sched/backfill
SelectType=select/cons_tres
SelectTypeParameters=CR_Core

# LOGGING
SlurmctldDebug=info
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdDebug=info
SlurmdLogFile=/var/log/slurm/slurmd.log
JobCompType=jobcomp/none

# ACCOUNTING
JobAcctGatherType=jobacct_gather/linux
JobAcctGatherFrequency=30
AccountingStorageType=accounting_storage/slurmdbd
AccountingStorageHost=localhost
#AccountingStorageLoc=
AccountingStoragePass=/var/run/munge/munge.socket.2
AccountingStorageUser=slurm

# COMPUTE NODES
NodeName=[HOST] CPUs=[NCPUs] Sockets=[NSOCKETS] RealMemory=[MEMORY] CoresPerSocket=[NCORES] ThreadsPerCore=[NTHREADS] Procs=1 State=UNKNOWN
PartitionName=normal Nodes=[HOST] Default=YES MaxTime=4320 State=UP
PartitionName=caesar Nodes=[HOST] Default=YES MaxMemPerCPU=10000 MaxTime=12:00:00 State=UP
```

To fill NodeName do:  

```bash
slurmd -C
```

#### Start the services   

```bash
sudo systemctl daemon-reload
sudo systemctl enable slurmd.service
sudo systemctl start slurmd.service
sudo systemctl enable slurmctld.service
sudo systemctl start slurmctld.service
```

### Configure `slurmdbd` accounting 

Slurm job accounting is handled by **SlurmDBD**, not by CAESAR-REST's `run_accounter.py` service. The latter is a separate application service for MongoDB-based usage statistics; see [CAESAR-REST accounting](accounting.md). The cluster must have a working SlurmDBD connection. 


#### Create and configure the slurm_acct_db database 

```bash
mysql -u root -p
```

```mysql
CREATE DATABASE IF NOT EXISTS slurm_acct_db;

CREATE USER 'slurm'@'localhost'
IDENTIFIED BY '<SET_A_STRONG_PASSWORD>';

GRANT ALL PRIVILEGES ON slurm_acct_db.*
TO 'slurm'@'localhost';
```

#### Set options in configuration file `/etc/slurm/slurmdbd.conf`:

```ini
AuthType=auth/munge
AuthAltTypes=auth/jwt
AuthAltParameters=jwt_key=/var/spool/slurmctld/jwt_hs256.key
DbdAddr=localhost
DbdHost=localhost
SlurmUser=slurm
DebugLevel=4
LogFile=/var/log/slurm/slurmdbd.log
PidFile=/var/run/slurmdbd.pid
StorageType=accounting_storage/mysql
StorageHost=localhost
StoragePass=[PASSWORD]
StorageUser=slurm
StorageLoc=slurm_acct_db
```

`localhost` is only correct if SlurmDBD runs on the same host as the component using that setting. 

#### Set file permissions   

```bash
sudo chown slurm:slurm /etc/slurm/slurmdbd.conf
sudo chmod 600 /etc/slurm/slurmdbd.conf
```

#### Enable and start the slurmdbd service   

```bash
sudo systemctl daemon-reload
sudo systemctl enable slurmdbd.service
sudo systemctl start slurmdbd.service
sudo systemctl status slurmdbd.service
```

#### Verify that accounting records are available, for example:

```bash
sacct -j JOB_ID --format=JobID,State,ExitCode
```

Use a real Slurm job ID. The command is an accounting-service check, not a CAESAR-REST API call.

### Configure `slurmrestd` service 

**This is required for CAESAR-REST's current monitoring and recovery behavior.** The service must load both plugins:

| Plugin | Endpoint prefix | Purpose in CAESAR-REST |
| --- | --- | --- |
| `openapi/v0.0.36` | `/slurm/v0.0.36` | Submit jobs, query jobs from the controller, and cancel jobs |
| `openapi/dbv0.0.36` | `/slurmdb/v0.0.36` | Read SlurmDBD accounting records for jobs no longer returned by the controller |

The existing CAESAR-REST Slurm client constructs these exact versioned paths. **Do not substitute a newer API version without updating and testing the client.** The plugins must be available in the particular Slurm installation; check the installed daemon's supported plugins and endpoints before enabling the unit.

#### Create a slurmrestd user

`caesar` is the service identity shown in the configuration files below, **not a universal recommendation**. Slurm recommends running `slurmrestd` under a dedicated unprivileged account, not as root or the Slurm service owner. Ensure the chosen account can access the required configuration and authentication facilities. 


#### Set slurmrestd config options inside `/etc/slurm/slurmrestd.conf`, including:

```ini
include /etc/slurm/slurm.conf
AuthType=auth/jwt
```

#### Set slurmrestd service file `slurmrestd.service` under `/etc/systemd/system/`:

```ini
[Unit]
Description=Slurm REST daemon for CAESAR-REST
After=network.target munge.service slurmctld.service slurmdbd.service
Wants=munge.service slurmctld.service slurmdbd.service
ConditionPathExists=/etc/slurm/slurm.conf

[Service]
Type=simple
User=caesar
Group=caesar
EnvironmentFile=-/etc/sysconfig/slurmrestd
Environment=SLURM_JWT=daemon
ExecStart=/usr/sbin/slurmrestd -f /etc/slurm/slurmrestd.conf -a rest_auth/jwt -s openapi/v0.0.36,openapi/dbv0.0.36 -vvvv 0.0.0.0:6820
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Adapt the following configuration file to your installed Slurm package and host. 
For site-specific overrides, prefer a systemd drop-in or a unit under `/etc/systemd/system/` rather than editing a vendor unit in `/usr/lib/systemd/system/`.

The `Environment=SLURM_JWT=daemon` setting follows Slurm's JWT listening-mode guidance; verify it against the behavior of the deployed release. The `-vvvv` verbosity is inherited from the historical deployment and is appropriate for diagnosis; reduce it for routine production operation.

**Security:** The example listens on all interfaces over HTTP (`0.0.0.0:6820`) because that matches the historic deployment. Restrict the listener using the cluster firewall and trusted network, or bind to a private interface. For access beyond a trusted network, put a correctly configured TLS/authenticating proxy in front of `slurmrestd`; do not expose the raw HTTP listener publicly. [Slurm's REST security guidance](https://slurm.schedmd.com/rest.html) provides further details.

#### Enable and start the slurmrestd service   

```bash
sudo systemctl daemon-reload
sudo systemctl enable slurmrestd.service
sudo systemctl start slurmrestd.service
sudo systemctl status slurmrestd.service
sudo journalctl -u slurmrestd.service -n 100 --no-pager
```

### Verify REST endpoints

Using a valid Slurm JWT for an authorized user, verify **both** APIs (openapi/v0.0.36, openapi/dbv0.0.36) from the CAESAR-REST host or another permitted machine:

```bash
export SLURM_REST_HOST="SLURM_HOST"
export SLURM_REST_PORT="6820"
export SLURM_USER_NAME="SLURM_USER"
# Populate SLURM_JWT securely with a valid, short-lived token.

curl --fail-with-body -sS \
  -H "X-SLURM-USER-NAME: ${SLURM_USER_NAME}" \
  -H "X-SLURM-USER-TOKEN: ${SLURM_JWT}" \
  "http://${SLURM_REST_HOST}:${SLURM_REST_PORT}/slurm/v0.0.36/jobs"

curl --fail-with-body -sS \
  -H "X-SLURM-USER-NAME: ${SLURM_USER_NAME}" \
  -H "X-SLURM-USER-TOKEN: ${SLURM_JWT}" \
  "http://${SLURM_REST_HOST}:${SLURM_REST_PORT}/slurmdb/v0.0.36/job/JOB_ID"
```

Replace `JOB_ID` with a numeric job ID for which an accounting record should exist. Inspect the JSON **`errors`** field even on an HTTP 200 response. If the controller endpoint works but the accounting endpoint does not, check that `openapi/dbv0.0.36` is loaded, that SlurmDBD is running, that accounting is enabled, and that JWT authentication to SlurmDBD is configured correctly.

## Configure CAESAR-REST for Slurm

CAESAR-REST selects Slurm by default, but an explicit `--job_scheduler=slurm` is useful in deployment scripts. Important application options include:

| Application option | Description |
| --- | --- |
| `--slurm_host` / `--slurm_port` | Address and port of the Slurm REST daemon (port default: `6820`) |
| `--slurm_user` | Slurm identity used by CAESAR-REST |
| `--slurm_keyfile` | Key material used by the current Slurm client to generate its JWT |
| `--slurm_queue` | Target partition/queue |
| `--slurm_batch_workdir` | Cluster directory for generated batch logs |
| `--slurm_jobdir`, `--slurm_datadir`, `--slurm_modeldir` | Job, data and model paths as visible to the cluster |
| `--slurm_max_cores_per_job` | Submission core limit |

See [CLI options](../reference/cli-options.md) and the implementation in `caesar_rest/slurm_client.py` for the complete interface. The client currently builds its base URL as `http://HOST:PORT/slurm/v0.0.36`; protect network access accordingly.

Application-side and cluster-side paths may differ. Configure both sides so submitted jobs can locate the expected inputs and output directories. Pipeline V2 stages additionally require persistent artifact retention and consistent mappings to retained data: see [artifact retention](artifact-retention.md).

## Job monitoring and accounting recovery

Run `run_jobmonitor.py` as a **separate CAESAR-REST service**, configured with MongoDB, the same Slurm REST endpoint/credentials, and the selected scheduler. Its default scheduler is now `slurm`.

```bash
run_jobmonitor.py \
  --job_scheduler=slurm \
  --dbhost=127.0.0.1 \
  --dbport=27017 \
  --dbname=caesardb \
  --slurm_host=SLURM_HOST \
  --slurm_port=6820 \
  --slurm_user=SLURM_USER \
  --slurm_keyfile=/path/to/authorized/jwt.key
```

The monitor first queries the Slurm controller. For a **previously `RUNNING`** job missing from the controller result, it calls `SlurmJobManager.get_accounting_job_status()` on:

```text
GET /slurmdb/v0.0.36/job/{job_id}
```

The accounting response is used only if the returned job record matches the expected ID and can be normalized to a recognized terminal result (`SUCCESS`, `FAILURE`, `CANCELED`, or `TIMED-OUT`). Otherwise the monitor falls back to the historical `CLEARED` state: it does **not** assume success from a missing controller record. This behavior is implemented in `caesar_rest/job_monitor.py` and `caesar_rest/slurm_client.py`.

**Troubleshooting:** If jobs complete on Slurm but appear as `CLEARED` in CAESAR-REST, verify SlurmDBD accounting, the `openapi/dbv0.0.36` plugin, the expected job IDs, JWT access, and the accounting API response before changing the monitor's state-handling logic.

For multi-stage Pipeline V2 jobs, job monitoring and artifact retention are distinct services; downstream stages consume registered and retained artifacts. See [job monitoring](job-monitoring.md) and [artifact retention](artifact-retention.md). CAESAR-REST's separate `run_accounter.py` is documented under [accounting](accounting.md) and is **not** needed to expose SlurmDBD REST accounting.

## Operational checklist

1. Verify Munge, `slurmctld`, relevant `slurmd` instances and `slurmdbd` are healthy.
2. Verify the deployed Slurm REST daemon loads **both** `openapi/v0.0.36` and `openapi/dbv0.0.36`.
3. Test controller and accounting endpoints with authorized JWT credentials.
4. Confirm CAESAR-REST application and job monitor use the same Slurm endpoint and permitted identity.
5. Submit a test job, observe monitoring, and confirm its final state can be recovered through accounting if it disappears from the controller.
6. For Pipeline V2, confirm output registration, retention and downstream visibility.

## References

- [Slurm REST API details](https://slurm.schedmd.com/rest.html)
- [Slurm REST API quick start](https://slurm.schedmd.com/rest_quickstart.html)
- [Slurm `slurmrestd` manual](https://slurm.schedmd.com/slurmrestd.html)
- [Slurm JWT authentication](https://slurm.schedmd.com/jwt.html)
- [Original CAESAR-REST README archive](../archive/ORIGINAL_README.md)


