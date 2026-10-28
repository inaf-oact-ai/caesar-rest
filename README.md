<p align="left">
  <img src="share/CAESAR-REST_Architecture.png" alt="Software architecture"/ width="500" height="500">
</p>

# caesar-rest
caesar-rest is a REST-ful web service for astronomical source extraction and classification with the caesar source extractor [https://github.com/SKA-INAF/caesar]. The software is developed in python and consists of a few containerized microservices, deployable on standalone servers or on a distributed cloud infrastructure. The core component is the REST web application, based on the Flask framework and running behind a nginx+uwsgi http server, and providing APIs for managing the input data (e.g. data upload/download/removal) and source finding jobs (e.g. submit, get status, get outputs) with different job management systems (Kubernetes, Slurm, Celery). Additional services (AAI, user DB, log storage, job monitor, accounting) enable the user authentication, the storage and retrieval of user data and job information, the monitoring of submitted jobs, and the aggregation of service logs and user data/job stats.
Besides caesar, we also foresee to integrate other tools widely used in the radio community (e.g. Aegean, PyBDSF) and newly developed source finders based on deep learning models.    

### Scientific pipelines and agent orchestration

CAESAR-REST also provides an authenticated REST API for managing
multi-stage scientific pipelines on Slurm-based infrastructures.

The pipeline framework supports:

- Application-independent pipeline and experiment registration.
- Configurable scientific stages and execution parameters.
- Multiple alternative runs per logical pipeline node.
- Named input artifacts and immutable cross-stage dependencies.
- Registration and retention of file and directory artifacts.
- Selection of preferred completed runs, including concurrency-safe updates.
- Explicit scientific, artifact-readiness and submission-state reporting.
- One-shot job submission with safeguards against duplicate Slurm execution.

These capabilities support agent-driven scientific workflows, where
external orchestration systems such as MAASAI propose experiments,
evaluate results, select preferred runs and decide which stage to
execute next.

The API does not automatically select scientifically optimal runs
or execute downstream stages. These decisions remain under the
control of the orchestrating application.

See:

- [Pipeline V2 REST API](docs/pipeline_v2_api.md)
- [MAASAI integration guide](docs/maasai_integration.md)


## **Status**
This software is under development. Original implementation developed in python 2.7, switched to python 3.6 later on (some apps are only available for python 3), now testing on python 3.8/3.10.

## **Credit**
This software is distributed with GPLv3 license. If you use caesar-rest for your research, please add repository link or acknowledge authors in your papers.   

## **Installation**  

### **Install dependencies**
To run caesar rest service you need to install the following tools:  

* Flask [https://palletsprojects.com/p/flask/]     
* uwsgi [https://uwsgi-docs.readthedocs.io/en/latest/index.html]   
* nginx [https://nginx.org/]   
* mongodb [https://www.mongodb.com/]   
* flask-pymongo python module [https://flask-pymongo.readthedocs.io/en/latest/]  
* structlog python module [https://www.structlog.org/en/stable/]     

For the Celery-based job management, you need to install celery, a broker and a result backend service:   

* celery [http://www.celeryproject.org/]   
* broker: rabbitmq [https://www.rabbitmq.com/]    
* result backend: redis [https://redis.io/] or mongodb [https://www.mongodb.com/]     

For the Kubernetes-based job management, you need to install the Kubernetes python client library:    

* kubernetes [https://pypi.org/project/kubernetes/]

For the Slurm-based job management, you need to install these python modules:    

* requests [https://docs.python-requests.org/en/master/]    
* jwt [https://pypi.org/project/jwt/]     

To enable OpenID Connect based authentication you need to install:    

* flask-oidc-ex python module fork [https://github.com/inaf-oact-ai/flask-oidc-ex]. The fork includes compatibility fixes required by current Flask/Werkzeug deployments. CAESAR-REST installs this dependency directly from the fork's `master` branch.

To enable log forwarding to a LogStash/ElasticSearch service, you need to install the filebeat service:    

* filebeat [https://www.elastic.co/guide/en/beats/filebeat/index.html]    

### **Package installation**
To build and install the package:    

* Create a local install directory, e.g. ```$INSTALL_DIR```
* Add installation path to your ```PYTHONPATH``` environment variable:   
  ``` export PYTHONPATH=$PYTHONPATH:$INSTALL_DIR/lib/python3.6/site-packages ```
* Build and install package:   
  ``` python3.6 setup.py sdist bdist_wheel```    
  ``` python3.6 setup build```   
  ``` python3.6 setup install --prefix=$INSTALL_DIR```   

All dependencies will be automatically downloaded and installed in ```$INSTALL_DIR```.   
     
To use package scripts:

* Add binary directory to your ```PATH``` environment variable:   
  ``` export PATH=$PATH:$INSTALL_DIR/bin ```    

### **App containers**
Apps are run as Docker (Kuberneter deploy) or Singularity (Slurm deploy) containers. Docker images are available in DockerHub:   

* `caesar` source finder job: `docker://sriggi/caesar-job`   
* `caesar-yolo` radio source finder based on YOLO object detector: `docker://sriggi/caesar-yolo-job`  
* `aegean` source finder job: `docker://sriggi/aegean-job`
* `cutex` source finder job: `docker://sriggi/cutex-job`
* `mrcnn` object detector (TensorFlow 1.x): `docker://sriggi/mrcnn-detect`
* `classifier-cnn` CNN image classifier (TensorFlow 2.x): `docker://sriggi/cnn-classifier`
* `classifier-vit` ViT image classifier (PyTorch 2.x + Transformers): `docker://sriggi/vit-classifier`
* `umap` dimensionality reduction: `docker://sriggi/umap-job`  
* `outlier-finder` with Isolation Forest: `docker://sriggi/outlier-finder-job`   
* `hdbscan` cluster search: `docker://sriggi/hdbscan-job`
* `similarity-search`: image similarity search: `docker://sriggi/similarity-search-job`   
* `sfforecaster`: solar flare forecasting with pre-trained foundation models: `sriggi/sfforecaster-job`  
* `fextractor`: image/light-curve feature extractor with pre-trained foundation models: 
      - TensorFlow ResNet image models: `sriggi/fextractor-tf`   
      - PyTorch ResNet/ViT image models: `sriggi/fextractor-torch`   
      - Google Chronos2 timeseries model: `sriggi/fextractor-chronos`   
      - Moirai2 timeseries model: `sriggi/fextractor-moirai`  
      - FATS timeseries library: `sriggi/fextractor-fats`  
      - LiCU timeseries library & models: `sriggi/fextractor-licu`    
      - Falcon timeseries model: `sriggi/fextractor-falcon`   

Singularity containers can be created from docker images with:   

```singularity pull [DOCKER URL]```

Try to change these Singularity environment variables in case you don't have enough disk space for building the containers in the Singularity default cache/tmp directories:   

```SINGULARITY_CACHEDIR```    
```SINGULARITY_TMPDIR```    

**NB: You may experience this error when running Singularity containers that produces large outputs (e.g. hundreds or MB or more): `OSError: [Errno 28] No space left on device`. Try to increase the default value (64 MB) of the `sessiondir max size` parameter in Singularity configuration file `/usr/local/etc/singularity/singularity.conf`.**      

## **How to run the service?**  

In the following we describe the steps done to deploy and run the application and the auxiliary services. Three possible options are described below for the deployment, depending of whether the job management is done with celery, Kubernetes, or with Slurm. To ease the deployment we provide Docker containers and configuration files for Docker Compose or Kubernetes.       

### **Preliminary setup**
Before running the application you must do some preparatory stuff:   

* (OPTIONAL) Create a dedicated user & group (e.g. `caesar`) allowed to run the application and services and give it ownership to the directories created below    * Create the application working dir (by default `/opt/caesar-rest`)   
* (OPTIONAL) Mount an external storage in the application working dir, for example using rclone: `/usr/bin/rclone mount --daemon [--uid=[UID] --gid=[UID]] --umask 000 --allow-other --file-perms 0777 --dir-cache-time 0m5s --vfs-cache-mode full [RCLONE_REMOTE_STORAGE]:[RCLONE_REMOTE_STORAGE_PATH] /opt/caesar-rest -vvv` where `UID` is the Linux user id of the user previously created.     
* Create the top directory for data upload (by default `/opt/caesar-rest/data`). Place here also supported pre-configured datasets.       
* Create the top directory for jobs (by default `/opt/caesar-rest/jobs`)    
* Create the top directory for models (by default `/opt/caesar-rest/models`) and put TensorFlow/PyTorch model & weights files under this path.        
* (OPTIONAL) Create the log directory for system services (see below), e.g. `/opt/caesar-rest/logs` 
* (OPTIONAL) Create the run directory for system services (see below), e.g. `/opt/caesar-rest/run` 
* Create a persistent directory for pipeline artifacts, e.g.
  `/storage/caesar-rest/pipeline-artifacts`. This directory must be
  accessible to the artifact retention worker, REST application
  and downstream staging environment.

### **Run DB service**
caesar-rest requires a MongoDB service where to store user data and job information. To start the DB service:    

```systemctl start mongodb.service```   

Alternatively you can use the Docker container ```sriggi/caesar-rest-db:latest``` (see https://hub.docker.com/r/sriggi/caesar-rest-db) and deploy it with DockerCompose or Kubernetes (see the configuration files under the repository ```config``` directory.   

### **Run Filebeat service (OPTIONAL)**   
caesar-rest uses filebeat to forward file logs to an ElasticSearch service. To start the service:   

```systemctl start filebeat.service```    

Alternatively, you can use the Docker container for the application ```sriggi/caesar-rest:latest``` (see https://hub.docker.com/r/sriggi/caesar-rest) setting the container option ```FORWARD_LOGS=1```. This will start the filebeat service in the web application container.   

### **Run Celery services (OPTIONAL)**
If you want to manage jobs with Celery, you must run a message broker service (i.e. rabbitmq), a task store service (i.e. redis or mongdb) and one or more Celery worker services.   
**NB: Celery job management option is not developed and maintained anymore in caesar-rest application. We suggest to use Slurm or Kubernetes deployment.**    

#### **Run broker service**   
To run the rabbimq message broker service:   
   
```systemctl start rabbitmq-server.service```   

Alternatively, you can use the Docker container ```sriggi/caesar-rest-broker:latest``` (see https://hub.docker.com/r/sriggi/caesar-rest-broker) and deploy it with DockerCompose or Kubernetes (see the configuration files under the repository ```config``` directory.      
   
#### **Run task store service**   
If you have chosen MongoDB as task store, you are already running the service (see previous section `Run DB service`). However, if you want to use Redis as task store, run it as follows:       
  
```systemctl start redis.service```    

Docker container is still to be produced.   
   
#### **Run celery workers**   
Run celery worker with desired concurrency level (e.g. 2), message queue (e.g. celery), broker and result backend urls:  
   
```celery --broker=[BROKER_URL] --result-backend=[RESULT_BACKEND_URL] --app=caesar_rest worker --loglevel=INFO --concurrency=2 -Q celery```   
   
In production you may want to run this as a system service:   
       
* Create a `/etc/default/caesar-workers` configuration file (e.g. see the example in the `config/celery` directory):  
   
     ```
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
     
* Create a `/etc/systemd/system/caesar-workers.service` systemd service file:    
   
     ```
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
  
* Start the service:   
  
     ```systemctl start caesar-workers.service```    
     
Alternatively, you can use the Docker container ```sriggi/caesar-rest-worker:latest``` (https://hub.docker.com/r/sriggi/caesar-rest-worker) and deploy it with DockerCompose or Kubernetes (see the configuration files under the repository ```config``` directory.      

### **Run Slurm services (OPTIONAL)**   
If you want to manage jobs with Slurm, you must run the following services:    

```systemctl start munge.service```    
```systemctl start slurmd.service```   
```systemctl start slurmdbd.service```    
```systemctl start slurmctld.service```   
```systemctl start slurmrestd.service```    

Below, we report a sample configuration file (`/usr/lib/systemd/system/slurmrestd.service`) for the Slurm REST service:    

```
[Unit]
Description=Slurm REST daemon
After=network.target munge.service slurmctld.service
ConditionPathExists=/etc/slurm/slurm.conf

[Service]
Type=simple
User=caesar
Group=caesar
EnvironmentFile=-/etc/sysconfig/slurmrestd
# Default to local auth via socket
ExecStart=/usr/sbin/slurmrestd -f /etc/slurm/slurmrestd.conf -a rest_auth/jwt -s openapi/v0.0.36 -vvvv 0.0.0.0:6820
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```

**NB: Slurm is currently the suggested job management option for caesar-rest application.**


### **Run the web application**   

#### **Run the application in development mode**   
To run caesar-rest in development mode, e.g. for debug or testing purposes:   

  ```$INSTALL_DIR/bin/run_app.py --[ARGS]```

where supported `ARGS` are:    

   MAIN OPTIONS       
   * `datadir=[DATADIR]`: Directory where to store uploaded data (default: /opt/caesar-rest/data)   
   * `jobdir=[JOBDIR]`: Top directory where to store job data (default: /opt/caesar-rest/jobs)     
   * `job_scheduler=[SCHEDULER]`:  Job scheduler to be used. Options are: {celery,kubernetes,slurm} (default=celery)     
   * `debug`: Run Flask application in debug mode if given   
   * `ssl`: To enable run of Flask application over HTTPS     

   AAI OPTIONS
   * `aai`: Enable service authentication    
   * `secretfile=[SECRETFILE]`: File (.json) with OpenID Connect client auth credentials   
   * `openid_realm=[REALM]`: OpenID Connect realm name (e.g. `caesar`)    
   
   DB OPTIONS       
   * `dbname=[DBNAME]`: Name of MongoDB database (default=caesardb)   
   * `dbhost=[DBHOST]`: Host of MongoDB database (default=localhost)    
   * `dbport=[DBPORT]`: Port of MongoDB database (default=27017)   

   LOGGING OPTIONS
   * `loglevel=[LEVEL]`: Log level to be used (default=INFO)   
   * `logtofile`: Enable logging to file (default=no)   
   * `logdir`: Directory where to store logs (default=/opt/caesar-rest/logs)   
   * `logfile`: Name of json log file (default=app_logs.json)   
   * `logfile_maxsize`: Max file size in MB (default=5)    
  
   CELERY OPTIONS       
   * `result_backend_host=[BACKEND_HOST]`: Host of Celery result backend service (default=localhost) 
   * `result_backend_port=[BACKEND_PORT]`: Port of Celery result backend service (default=6379)   
   * `result_backend_proto=[BACKEND_PROTO]`: Celery result backend type. Options are: {mongodb,redis} (default=redis)   
   * `result_backend_dbname=[BACKEND_DBNAME]`: Celery result backend database name (default=0)   
   * `broker_host=[BROKER_HOST]`: Host of Celery broker service (default=localhost)    
   * `broker_port=[BROKER_PORT]`: Port of Celery broker service (default=5672)    
   * `broker_proto=[BROKER_PROTO]`: Protocol of Celery broker. Options are: {amqp,redis} (default=amqp)    
   * `broker_user=[BROKER_USER]`: Username used in Celery broker (default=guest)   
   * `broker_pass=[BROKER_PASS]`: Password used in Celery broker (default=guest)   
  
   KUBERNETES OPTIONS   
   * `kube_config=[FILE_PATH]`: Kube configuration file path (default=search in standard path)   
   * `kube_cafile=[FILE_PATH]`: Kube certificate authority file path    
   * `kube_keyfile=[FILE_PATH]`: Kube private key file path    
   * `kube_certfile=[FILE_PATH]`: Kube certificate file path   

   SLURM OPTIONS   
   * `slurm_keyfile=[FILE_PATH]`: Slurm rest service private key file path    
   * `slurm_user=[SLURM_USER]`: Username enabled to run in Slurm cluster (default is deployment-specific)   
   * `slurm_host=[SLURM_HOST]`: Slurm cluster host/ipaddress (default=localhost)   
   * `slurm_port=[SLURM_PORT]`: Slurm rest service port (default=6820)  
   * `slurm_batch_workdir=[SLURM_BATCH_WORKDIR]`: Cluster directory where to place Slurm batch logs (must be writable by slurm_user) (default=/opt/slurm/batchlogs/caesar-rest)    
   * `slurm_queue=[SLURM_QUEUE]`: Slurm cluster queue for submitting jobs (default=normal)   
   * `slurm_jobdir=[SLURM_JOBDIR]`: Path at which the job directory is mounted in Slurm cluster (default=/mnt/storage/jobs)    
   * `slurm_datadir=[SLURM_DATADIR]`: Path at which the data directory is mounted in Slurm cluster (default=/mnt/storage/data)   
   * `slurm_max_cores_per_job=[SLURM_MAX_CORES_PER_JOB]`: Slurm maximum number of cores reserved for a job (default=4)   
    
   VOLUME MOUNT OPTIONS   
   * `mount_rclone_volume`: Enable mounting of Nextcloud volume through rclone in container jobs (default=no)  
   * `mount_volume_path=[PATH]`: Mount volume path for container jobs (default=/mnt/storage)  
   * `rclone_storage_name=[NAME]`: rclone remote storage name (default=neanias-nextcloud)   
   * `rclone_storage_path=[PATH]`: rclone remote storage path (default=.)

   SINGULARITY CONTAINER OPTIONS
   * `caesar_container`: Path to caesar job Singularity container (default=/opt/containers/caesar/caesar-job_latest.sif)   
   * `aegean_container`: Path to aegean job Singularity container (default=/opt/containers/aegean/aegean-job_latest.sif)   
   * `cutex_container`: Path to cutex job Singularity container (default=/opt/containers/cutex/cutex-job_latest.sif)
   * `mrcnn_container`: Path to caesar-mrcnn job Singularity container (default=/opt/containers/mrcnn/mrcnn-detect_latest.sif)
   * `cnn_classifier_container`: Path to CNN classifier Singularity container (default=/opt/containers/sclassifier/cnn-classifier_latest.sif)
   * `vit_classifier_container`: Path to VIT classifier Singularity container (default=/opt/containers/sclassifier-vit/vit-classifier_latest.sif)
   * `umap_container`: Path to UMAP Singularity container (default=/opt/containers/sclassifier/umap_latest.sif)
   * `outlier_finder_container`: Path to OutlierFinder Singularity container (default=/opt/containers/sclassifier/outlier_finder_latest.sif)
   * `hdbscan_container`: Path to HDBSCAN Singularity container (default=/opt/containers/sclassifier/hdbscan_latest.sif)
   * `simsearch_container`: Path to Similarity Search Singularity container (default=/opt/containers/sclassifier/similarity-search_latest.sif)

   DATASET OPTIONS  
   * `dataset_smgps`: Path to smgps dataset json filelist
   * `dataset_smgps_feats_simclr`: Path to smgps_feats_simclr dataset json filelist   
   * `dataset_smgps_feats_siglip`: Path to smgps_feats_siglip dataset json filelist   
   * `dataset_smgps_feats_dinov2`: Path to smgps_feats_dinov2 dataset json filelist
   * `dataset_emu_pilot`: Path to emu-pilot dataset json filelist
   * `dataset_emu`: Path to emu dataset json filelist
   * `dataset_emu_scorpio_pilot`: Path to emu-scorpio-pilot dataset json filelist
   * `dataset_emu_gp_pilot`: Path to emu-gp-pilot dataset json filelist      
  
Flask default options are defined in the `config.py`. Celery options are defined in the `celery_config.py`. Other options may be defined in the future to override default Flask and Celery options.   
The default RabbitMQ `guest` credentials are intended for local
development only. Production deployments should use dedicated
accounts with strong credentials and restricted permissions.

#### **Run the application in production**   
In a production environment you can run the application behind a nginx+uwsgi (or nginx+gunicorn) server. In the `config` directory of the repository you can find sample files to create and configure required services. For example:  

* Start the application with uwsgi:   
     
  uwsgi --wsgi-file $INSTALL_DIR/bin/run_app.py --callable app [WSGI_CONFIG_FILE]

  where ```WSGI_CONFIG_FILE``` is a configuration file (.ini format) for uwsgi. A sample configuration file is provided in the `config/uwgsi` directory:   
  
  ```
  [uwsgi]
  processes = 4   
  threads = 2   
  socket = ./run/caesar-rest.sock   
  ;socket = :5000
  ;http-socket = :5000
  socket-timeout = 65
  
  buffer-size = 32768  
  master = true   
  chmod-socket = 660   
  vacuum = true  
  die-on-term = true  
  ```
  
  Alternatively you can configure options from command line, e.g.:    
  
   ```uwsgi --uid=[RUNUSER] --gid=[RUNUSER] --binary-path /usr/local/bin/uwsgi --wsgi-file=$INSTALL_DIR/bin/run_app.py --callable=app --pyargv=[APP_ARGS] --workers=[NWORKERS] --enable-threads --threads=[NTHREADS] --http-socket="0.0.0.0:[PORT]" --http-timeout=[SOCKET_TIMEOUT] --http-enable-proxy-protocol --http-auto-chunked --socket-timeout=[SOCKET_TIMEOUT] --master --chmod-socket=660 --chown-socket=[RUNUSER] --buffer-size=[BUFFER_SIZE] --vacuum --die-on-term ```
  
  where ```APP_ARGS``` are the application command line options described in the previous paragraph and ```RUNUSER``` is the username chosen for running the service. The other options are described in the uwsgi online documentation.    
  
  In production you may want to run this as a system service: 
  
  - Create an `/etc/systemd/system/caesar-rest.service` systemd service file, for example following the example provided in the `config/uwsgi` directory:       
       
    ```
    [Unit]
    Description=uWSGI instance to serve caesar-rest application    
    After=network.target caesar-workers.target   

    [Service]
    User=caesar  
    Group=www-data   
    WorkingDirectory=/opt/caesar-rest  
    Environment="PATH=$INSTALL_DIR/bin"   
    Environment="PYTHONPATH=$INSTALL_DIR/lib/python2.7/site-packages"  
    ExecStart=/usr/bin/uwsgi --wsgi-file $INSTALL_DIR/bin/run_app.py --callable app --ini /opt/caesar-rest/config/uwsgi.ini

    [Install]   
    WantedBy=multi-user.target    
    ```   
    
   - Start the service:   
     ```sudo systemctl caesar-rest.service start```    

   Alternatively, you can use the Docker container `sriggi/caesar-rest:devel` (see https://hub.docker.com/r/sriggi/caesar-rest) and deploy it with DockerCompose or Kubernetes (see the configuration files under the repository ```config``` directory. All application command line options described in the previous section can be configured from container env variables.        

* Start the nginx service:

  - Create a `/etc/nginx/conf.d/nginx.conf` configuration file (see example file provided in the `config/nginx` directory):      

    ```
    server {   
      listen 8080;   
      client_max_body_size 1000M;   
      sendfile on;    
      keepalive_timeout 0;   
      location / {   
        include uwsgi_params;    
        uwsgi_pass unix:/opt/caesar-rest/run/caesar-rest.sock;   
      }       
    }    
    ```
  
    With this sample configuration the nginx server will listen at port 8080 and call the caesar-rest application via socket. An alternative configuration could be:    
    
    ```
    upstream backend {
      least_conn;  # load balancing strategy
      server [HOST1]:[PORT];
      server [HOST1]:[PORT];
      keepalive 64;
    }

    server {
      listen 8080;
      client_max_body_size 1000M;
      large_client_header_buffers 4 32k;
      sendfile on;
      keepalive_timeout 0;
      location / {
        include uwsgi_params;
        uwsgi_pass backend;
      }
    }
    ```
    
    with nginx load balancing incoming requests, sending them to 2 caesar-rest http applications listening at `HOST1` and `HOST2` on port `PORT`.    
   
  - Create a `/etc/systemd/system/nginx.service` systemd file, e.g. see the example provided in the `config/nginx` directory:   
  
    ```
    [Unit]   
    Description=The NGINX HTTP and reverse proxy server  
    After=syslog.target network.target remote-fs.target nss-lookup.target caesar-rest.target   

    [Service]   
    Type=forking    
    PIDFile=/run/nginx.pid   
    ExecStartPre=/usr/sbin/nginx -t   
    ExecStart=/usr/sbin/nginx   
    ExecReload=/usr/sbin/nginx -s reload   
    ExecStop=/bin/kill -s QUIT $MAINPID   
    PrivateTmp=true    

    [Install]   
    WantedBy=multi-user.target   
    ```
  
  - Run nginx server:   

    ```sudo systemctl start nginx.service```

  Alternatively you can use the Docker container `sriggi/caesar-rest-lb:latest` (see https://hub.docker.com/r/sriggi/caesar-rest-lb) and deploy it with DockerCompose. In Kubernetes this functionality is provided by ingresses (see sample configuration files).   


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

### **Run job monitoring service**   
The job monitoring service periodically monitors user jobs, updating their status on the DB. 

For scientific pipeline runs, successful completion also triggers
output artifact registration. The standalone pipeline artifact
retention worker subsequently promotes registered outputs into
persistent storage.

Job monitoring and artifact retention are independent services:
the former tracks scientific execution, while the latter preserves
artifacts for downstream pipeline stages.

The job monitoring service can be started as:    

```$INSTALL_DIR/bin/run_jobmonitor.py --[ARGS]```    

where supported `ARGS` are:   

   * `job_monitoring_period=[PERIOD]`: Job monitoring poll period in seconds (default=30)     
   * `job_scheduler=[SCHEDULER]`:  Job scheduler to be used. Options are: {celery,kubernetes,slurm} (default=celery)     
   * `dbname=[DBNAME]`: Name of MongoDB database (default=caesardb)   
   * `dbhost=[DBHOST]`: Host of MongoDB database (default=localhost)    
   * `dbport=[DBPORT]`: Port of MongoDB database (default=27017)      
   * `kube_config=[FILE_PATH]`: Kube configuration file path (default=search in standard path)   
   * `kube_cafile=[FILE_PATH]`: Kube certificate authority file path    
   * `kube_keyfile=[FILE_PATH]`: Kube private key file path    
   * `kube_certfile=[FILE_PATH]`: Kube certificate file path   
   * `slurm_keyfile=[FILE_PATH]`: Slurm rest service private key file path    
   * `slurm_user=[SLURM_USER]`: Username enabled to run in Slurm cluster (default=cirasa)   
   * `slurm_host=[SLURM_HOST]`: Slurm cluster host/ipaddress (default=localhost)   
   * `slurm_port=[SLURM_PORT]`: Slurm rest service port (default=6820)  

Alternatively, you can use the Docker container `sriggi/caesar-rest-jobmonitor:latest` (see https://hub.docker.com/r/sriggi/caesar-rest-jobmonitor) and deploy it with DockerCompose or Kubernetes (see sample configuration files).    


### **Run pipeline artifact retention service**

CAESAR-REST provides a standalone artifact retention worker responsible
for preserving the outputs of completed scientific pipeline runs.

The service is implemented in `apps/run_artifact_retention.py` and runs
independently of the REST application and job monitoring service.

The pipeline artifact lifecycle consists of three main steps:

1. The scientific job completes successfully and its pipeline run
   transitions to `COMPLETED`.
2. The output artifacts are registered in MongoDB, including their
   names, types, sizes and integrity metadata.
3. The artifact retention worker copies and verifies registered
   artifacts into the configured persistent retention storage.

The retention worker processes completed, registered pipeline runs
whose artifacts have not yet been retained.

**For multi-stage Pipeline V2 execution, artifact retention is
required:** downstream stages consume retained upstream artifacts,
not arbitrary files from the original job working directory.

#### Starting the retention worker

After installing CAESAR-REST, start the service with:

```bash
$INSTALL_DIR/bin/run_artifact_retention.py \
  --dbhost=localhost \
  --dbport=27017 \
  --dbname=caesardb \
  --retention-root=/opt/caesar-rest/pipeline-artifacts \
  --poll-seconds=30
```

Replace the retention root with the absolute path configured for
your installation.

The retention root must be accessible and writable by the
retention worker. It must also be accessible to the REST service
and to the staging environment used for downstream pipeline runs.

The REST application and retention worker must be configured to
use the same MongoDB database and artifact retention storage.

#### Worker configuration

The retention worker accepts the following command-line options:

| Option | Description | Default |
|--------|-------------|---------|
| `--dbhost` | MongoDB hostname | `localhost` |
| `--dbport` | MongoDB port | `27017` |
| `--dbname` | MongoDB database name | `caesardb` |
| `--retention-root` | Absolute directory for persistent artifacts | Required |
| `--poll-seconds` | Polling interval in seconds | `30` |
| `--max-file-bytes` | Maximum size of an individual artifact file | `1073741824` (1 GiB) |
| `--max-directory-bytes` | Maximum size of a retained artifact directory | `1099511627776` (1 TiB) |
| `--max-directory-entries` | Maximum entries in a retained directory | `100000` |
| `--max-directory-depth` | Maximum artifact directory depth | `16` |

Size and directory limits should be configured according to
the requirements of the scientific applications being executed.

For example, radio-interferometric measurement sets can require
significant storage capacity and may contain many files.

#### Retention processing

The worker periodically queries MongoDB for eligible runs.

A run is eligible when:

- Its scientific status is `COMPLETED`.
- Its output artifacts have been registered.
- At least one artifact is registered.
- No retained artifact list has been published.
- Its retention status is absent or `PENDING`.

The worker atomically marks an eligible run as `COPYING` before
processing it.

Artifact promotion includes integrity checks. The retained
artifacts are published only after successful promotion.

On success, the run receives:

`retention_status = READY`

On failure, the worker records:

`retention_status = FAILED`

and stores diagnostic information in the run metadata.

Failed retention operations require investigation and recovery;
the worker does not automatically repeat failed copying operations.

For an initial deployment, run exactly one retention worker
instance. The existing per-run filesystem locking mechanism
provides additional protection, but a single worker is the
recommended initial configuration.

#### Monitoring artifact readiness

Clients can inspect the retention state using:

`GET /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}`

A successfully completed and retained run reports:

```json
{
  "status": "COMPLETED",
  "artifacts_status": "READY",
  "readiness": {
    "can_select": true,
    "can_consume": true
  }
}
```

A scientifically completed run may not immediately report
`can_consume = true`, because artifact registration and retention
are performed independently of scientific execution.

For agent-driven workflows such as MAASAI, downstream run
registration should be attempted only when the required
upstream artifacts are available. The artifact-binding layer
performs the authoritative integrity verification.

See the [Pipeline V2 API reference](docs/pipeline_v2_api.md)
for further details.

   
### **Run accounting service**   
The accounting service periodically monitors user data and job info, storing aggregated stats in the DB. It can be started as:    

```$INSTALL_DIR/bin/run_accounter.py --[ARGS]```    

where supported `ARGS` are:   

   * `datadir=[DATADIR]`: Directory where to store uploaded data (default: /opt/caesar-rest/data)   
   * `jobdir=[JOBDIR]`: Top directory where to store job data (default: /opt/caesar-rest/jobs)     
   * `job_monitoring_period=[PERIOD]`: Job info monitoring poll period in seconds (default=30) 
   * `dbname=[DBNAME]`: Name of MongoDB database (default=caesardb)   
   * `dbhost=[DBHOST]`: Host of MongoDB database (default=localhost)    
   * `dbport=[DBPORT]`: Port of MongoDB database (default=27017)      
   * `mount_rclone_volume`: Enable mounting of Nextcloud volume through rclone in container jobs (default=no)  
   * `mount_volume_path=[PATH]`: Mount volume path for container jobs (default=/mnt/storage)  
   * `rclone_storage_name=[NAME]`: rclone remote storage name (default=neanias-nextcloud)   
   * `rclone_storage_path=[PATH]`: rclone remote storage path (default=.)   

Alternatively, you can use the Docker container `sriggi/caesar-rest-accounter:latest` (see https://hub.docker.com/r/sriggi/caesar-rest-accounter) and deploy it with DockerCompose or Kubernetes (see sample configuration files).    


## Scientific Pipeline V2 API

CAESAR-REST provides an authenticated API for registering,
executing and monitoring multi-stage scientific pipelines.

The pipeline API is application-independent. Scientific stages,
allowed parameters and input mappings are configured on the
server. The examples below use OXKAT, but the same pipeline
infrastructure can support other scientific applications.

All endpoints use the prefix:

`/caesar/api/v1.0`

Pipeline requests require authentication. REST clients should
provide a valid access token:

`Authorization: Bearer <access-token>`

Refer to the Keycloak/OpenID Connect section above for
authentication and TLS configuration.

### Pipeline concepts

A **pipeline** groups related scientific experiments.

A **stage** identifies the scientific processing operation
(e.g. GET_INFO, 1GC, FLAG or 2GC for OXKAT).

A **node** groups alternative runs for the same stage.
Different nodes may represent independent experimental groups
for the same scientific stage. For example, an agent may use
`flag_conservative` and `flag_aggressive` as separate nodes
for the OXKAT `FLAG` stage.

Each node maintains its own preferred-run selection.

If `node_id` is omitted, CAESAR-REST assigns a generic
identifier such as `stage_flag` or `stage_2gc`.

A **run** represents a registered experiment with fixed
scientific parameters and input dependencies.

A **selected run** is the preferred completed experiment
within a node. Selection is mutable, but previously registered
downstream input bindings remain immutable.

### Core REST endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/pipelines` | Create a pipeline |
| GET | `/pipelines` | List pipelines |
| GET | `/pipelines/{pipeline_id}` | Retrieve pipeline metadata |
| GET | `/pipelines/{pipeline_id}/runs` | List pipeline runs |
| POST | `/pipelines/{pipeline_id}/runs` | Register a V2 run |
| GET | `/pipelines/{pipeline_id}/runs/{run_id}` | Retrieve run details and readiness |
| POST | `/pipelines/{pipeline_id}/runs/{run_id}/submit` | Submit a registered run |
| GET | `/pipelines/{pipeline_id}/tree` | Retrieve pipeline execution tree |
| POST | `/pipelines/{pipeline_id}/sync` | Synchronize run states |
| POST | `/pipelines/{pipeline_id}/nodes/{node_id}/selection` | Select a completed run unconditionally |
| PUT | `/pipelines/{pipeline_id}/nodes/{node_id}/selection` | Conditionally select a completed run |

Additional node-oriented run, artifact listing, artifact download,
selected-artifact resolution and retention endpoints are documented
in the [Pipeline V2 API reference](docs/pipeline_v2_api.md).

### Quick start

#### 1. Create a pipeline

`POST /caesar/api/v1.0/pipelines`

```json
{
  "app": "oxkat",
  "name": "OXKAT calibration experiments",
  "description": "Agent-driven calibration and imaging"
}
```

The response contains a `pipeline_id`.

#### 2. Register an initial run

`POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs`

```json
{
  "stage": "GET_INFO",
  "dataset_id": "oxkat-test-dataset-v3"
}
```

This creates a `PLANNED` run; it does not submit a job.

#### 3. Submit the registered run

`POST /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}/submit`

```json
{}
```

CAESAR-REST derives the execution request from the registered
run. Clients do not resubmit scientific parameters or storage paths.

#### 4. Monitor the run

`GET /caesar/api/v1.0/pipelines/{pipeline_id}/runs/{run_id}`

The response includes:

```json
{
  "status": "COMPLETED",
  "artifacts_status": "READY",
  "readiness": {
    "can_select": true,
    "can_consume": true
  },
  "submission": {
    "state": "ACCEPTED",
    "retry_allowed": false,
    "requires_reconciliation": false
  }
}
```

These values illustrate a successfully completed and retained run.

`COMPLETED` describes scientific execution. `READY` indicates
that the registered outputs have complete retained-artifact
metadata. Actual downstream input binding still verifies artifact
availability and integrity.

The submission state `ACCEPTED` does not by itself mean that
the scientific execution succeeded.

#### 5. Register a downstream run with named inputs

A typical OXKAT calibration pipeline progresses through:

`GET_INFO → 1GC → FLAG → 2GC`

Each stage produces registered scientific artifacts that can be
consumed by subsequent stages. The orchestrating application
decides whether to execute another experiment, select a preferred
run or proceed to the next scientific stage.

The examples below focus on 2GC input registration. See the
MAASAI integration guide for the complete orchestration workflow.

A later OXKAT stage can reference concrete artifacts from
an upstream run:

```json
{
  "stage": "2GC",
  "inputs": {
    "target_ms": {
      "run_id": "FLAG_RUN_ID",
      "artifact": "flagged_target_measurement_sets"
    },
    "flag_images": {
      "run_id": "FLAG_RUN_ID",
      "artifact": "flag_images"
    },
    "project_info": {
      "run_id": "FLAG_RUN_ID",
      "artifact": "project_info"
    }
  }
}
```

Alternatively, the client can reference the currently selected
run of a logical node:

```json
{
  "stage": "2GC",
  "inputs": {
    "target_ms": {
      "node_id": "flag",
      "selected": true,
      "artifact": "flagged_target_measurement_sets"
    },
    "flag_images": {
      "node_id": "flag",
      "selected": true,
      "artifact": "flag_images"
    },
    "project_info": {
      "node_id": "flag",
      "selected": true,
      "artifact": "project_info"
    }
  }
}
```

The selected run is resolved at registration time. The server
stores immutable upstream run IDs, artifact indices and integrity
metadata. Later changes to a preferred selection do not affect
previously registered downstream runs.

The node identifier must match an existing node in the pipeline.

### Preferred-run selection

To select a completed run unconditionally:

`POST /pipelines/{pipeline_id}/nodes/{node_id}/selection`

```json
{
  "run_id": "PREFERRED_RUN_ID"
}
```

For concurrency-safe updates, use PUT:

`PUT /pipelines/{pipeline_id}/nodes/{node_id}/selection`

```json
{
  "run_id": "NEW_PREFERRED_RUN_ID",
  "expected_run_id": "CURRENT_PREFERRED_RUN_ID"
}
```

The operation succeeds only if the current selection matches
`expected_run_id`. Otherwise the server returns HTTP 409.

Set `expected_run_id` to JSON `null` when the node is expected
to have no selected run.

Conditional selection is recommended for concurrent agents.

### Submission safety

Pipeline V2 uses atomic run claims and durable one-shot
submission intents to prevent duplicate scheduler submissions.

A timed-out HTTP request does not necessarily mean that Slurm
rejected the submission.

Clients should retrieve the run status and inspect the
`submission` object before taking further action.

For uncertain submissions, automatic resubmission is not safe.
Reconciliation may be required. 

The `submission.retry_allowed` field indicates whether the
stored run state permits an initial submission attempt.

When `retry_allowed` is `true` for a `PLANNED` run, the server
still performs atomic claiming and all normal submission checks.

This field must not be interpreted as authorization to
automatically retry a timed-out HTTP submission request.

Runs in `SUBMITTING`, `SUBMITTED`, `SUBMISSION_FAILED` or
`SUBMISSION_UNCERTAIN` must not be blindly resubmitted.

### Artifact lifecycle

Scientific completion, artifact registration, retention and
preferred-run selection are separate operations.

A completed run may be selected before its outputs are retained,
but downstream stages require retained and verified input artifacts.

CAESAR-REST maintains frozen artifact identities and integrity
metadata so that downstream runs consume the intended outputs
even when preferred selections change.

### Detailed documentation

- [Pipeline V2 API reference](docs/pipeline_v2_api.md)
- [MAASAI integration guide](docs/maasai_integration.md)

The API reference documents the complete route set, artifact
operations, run lifecycle, validation rules and error handling.

The MAASAI guide explains agent-oriented registration, submission,
monitoring, experiment comparison, selected-run resolution and
safe recovery from ambiguous submission outcomes.

---



## **Usage**  
caesar-rest provides the following REST endpoints:   

**Authentication:** When AAI is enabled, REST API requests must include a valid OAuth2 bearer access token in the `Authorization` header:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

Unless otherwise specified, the endpoint examples below assume AAI is disabled. For authenticated deployments, include the authorization header as described in the [Keycloak / OpenID Connect Authentication](#keycloak--openid-connect-authentication-aai) section.

### **Data upload**

* URL:```http://server-address:port/caesar/api/v1.0/upload```   
* Request methods: POST   
* Request header: ```content-type: multipart/form-data```   

A sample curl request would be:   

```
curl -X POST \   
  -H 'Content-Type: multipart/form-data' \   
  -F 'file=@VGPS_cont_MOS017.fits' \   
  --url 'http://localhost:8080/caesar/api/v1.0/upload'   
```

Server response is:   
```
{
  "date":"2020-04-24T17:04:26.174333",
  "filename_orig":"VGPS_cont_MOS017.fits",
  "format":"fits",
  "size":4.00726318359375,
  "status":"File uploaded with success",
  "uuid":"250fdf5ed6a044888cf4406338f9e73b"
}
```

A file uuid (or file path) are returned and can be used to download the file or set job input file information.   

### **Data download**

* URL:```http://server-address:port/caesar/api/v1.0/download/[file_id]```   
* Request methods: GET, POST   
* Request header: None  

A sample curl request would be:   

```
curl  -X GET \
  --fail -o data.fits \
  --url 'http://localhost:8080/caesar/api/v1.0/download/67a49bf7555b41739095681bf52a1f99'
```

The above request will fail if file is not found, otherwise the downloaded file will be saves as `data.fits`. Without the `-o` argument raw output is written to stdout. If file is not found a json response is returned:   

```
{
  "status": "File with uuid 67a49bf7555b41739095681bf52a1f99 not found on the system!"
}
```

### **Get uploaded data ids**

* URL:```http://server-address:port/caesar/api/v1.0/fileids```   
* Request methods: GET   
* Request header: None  

A sample curl request would be:   

```
curl  -X GET \
  --url 'http://localhost:8080/caesar/api/v1.0/fileids'
```

with response:    

```
{"file_ids":["a668c353ba4d4c7395ad94b4e8647d92","c54db5ef95734c62a499db38587c48a5","26bc9a545c8f4f05a2c719ec5c3917e0"]}
```

### **Dataset list & description**
To get the list of supported datasets: 

* URL:```http://server-address:port/caesar/api/v1.0/datasets```   
* Request methods: GET   
* Request header: none

Server response contains a list of configured datasets that can be used as inputs in job submission:   

```
{
  "smgps": {
    "description": "A collection of 178,057 image cutouts of size 256x256 pixels extracted from the SARAO MeerKAT Galactic Plane survey (Goedhart+24)."
  },
  "smgps-feats-simclr": {
    "description": "Feature data (#512 features) obtained with a SimCLR self-supervised pre-trained model from a collection of 178,057 image cutouts of size 256x256 pixels extracted from the SARAO MeerKAT Galactic Plane survey (Goedhart+24)."
  }
}
```

### **App list**
To get the list of supported apps:   

* URL:```http://server-address:port/caesar/api/v1.0/apps```   
* Request methods: GET   
* Request header: none

Server response contains a list of valid apps that can be queried for further description and used in job submission:    

```
{
  "apps": [
    "caesar",
    "mrcnn",
    "aegean",
    "cutex",
    "classifier-cnn",
    "classifier-vit",
    "featextractor-simclr",
    "umap",
    "outlier-finder",
    "hdbscan",
    "similarity-search"	
  ]
}
```

### **App description**
To get information about a given app:  

* URL:```http://server-address:port/caesar/api/v1.0/app/[app_name]/describe```   
* Request methods: GET    
* Request header: none

Server response contains a list of app options that can be used in job submission. Below we report a description of the `umap` app (url: `http://server-address:port/caesar/api/v1.0/app/umap/describe`):   
```
{
	"datalist-key": {
		"advanced": 0,
		"category": "INPUT",
		"default": "data",
		"description": "Dictionary key name to be read in input datalist (default=data)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	},
	"mindist": {
		"advanced": 0,
		"category": "PROCESSING",
		"default": 0.1,
		"description": " Min dist UMAP parameter (default=0.1)",
		"enum": false,
		"mandatory": false,
		"max": 1.0,
		"min": 0.0,
		"subcategory": "",
		"type": "float"
	},
	"nfeats": {
		"advanced": 0,
		"category": "PROCESSING",
		"default": 2,
		"description": "Encoded data dim in UMAP (default=2)",
		"enum": false,
		"mandatory": false,
		"max": 512,
		"min": 2,
		"subcategory": "",
		"type": "int"
	},
	"nneighbors": {
		"advanced": 0,
		"category": "PROCESSING",
		"default": 15,
		"description": "N neighbors UMAP parameter (default=15)",
		"enum": false,
		"mandatory": false,
		"max": 10000,
		"min": 1,
		"subcategory": "",
		"type": "int"
	},
	"no-logredir": {
		"advanced": 0,
		"category": "RUN",
		"description": "Do not redirect logs to output file in script",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"no-save-ascii": {
		"advanced": 0,
		"category": "OUTPUT",
		"description": "Do not save output in ascii format",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"no-save-json": {
		"advanced": 0,
		"category": "OUTPUT",
		"description": "Do not save output in json format",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"no-save-model": {
		"advanced": 0,
		"category": "OUTPUT",
		"description": "Do not save model",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"normalize_minmax": {
		"advanced": 0,
		"category": "PREPROCESSING",
		"description": "Normalize each channel in range",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"outfile-sup": {
		"advanced": 0,
		"category": "OUTPUT",
		"default": "featdata_umap_sup.dat",
		"description": "Name of UMAP encoded data output file for supervised run in ascii format (default=featdata_umap_sup.dat)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	},
	"outfile-unsup": {
		"advanced": 0,
		"category": "OUTPUT",
		"default": "featdata_umap.dat",
		"description": "Name of UMAP encoded data output file in ascii format (default=featdata_umap.dat)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	},
	"outfile-unsup-json": {
		"advanced": 0,
		"category": "OUTPUT",
		"default": "featdata_umap.json",
		"description": "Name of UMAP encoded data output file in json format (default=featdata_umap.json)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	},
	"run-supervised": {
		"advanced": 0,
		"category": "RUN",
		"description": "Run UMAP also on labelled data alone (if available)",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"selcols": {
		"advanced": 0,
		"category": "INPUT",
		"default": "",
		"description": "Data column ids to be selected from input data, separated by commas (default=all columns)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	}
}

```

### **Job submission**
* URL:```http://server-address:port/caesar/api/v1.0/job```   
* Request methods: POST   
* Request header: ```content-type: application/json```   

A sample curl request for running the `caesar` source finder app would be:   

```
curl -X POST \   
  -H 'Content-Type: application/json' \   
  -d '{"app": "caesar","data_inputs": {"data": "39ca08fc5c7c446d8756a48088ee684c"},"job_options": {"run": true,"no-logredir": true,"no-mpi": true,"no-nestedsearch": true,"no-extendedsearch": true}}' \   
  --url 'http://localhost:8080/caesar/api/v1.0/job'   
```

Job data must contain a valid app name (in this case `caesar`) and desired job inputs, e.g. a dictionary with app valid options. Valid options for `caesar` app are named as in `caesar` and can be retrieved using app description url described above.   

Server response is:   

```
{
  "app": "caesar",
  "data_inputs": "39ca08fc5c7c446d8756a48088ee684c",
  "job_id": "a4095b815a074d81a0cc447762aa29f1",
  "job_options": {
    "no-extendedsearch": true,
    "no-logredir": true,
    "no-mpi": true,
    "no-nestedsearch": true,
    "run": true
   },
   "state": "PENDING",
   "status": "Job submitted and registered with success",
   "submit_date": "2024-12-19T10:00:42.865802",
   "tag": ""
}
```

A job id is returned in the response which can be used to query the status of the job or cancel it or retrieve output data at completion. 

### **Get job status**
* URL:```http://server-address:port/caesar/api/v1.0/job/[job_id]/status```   
* Request methods: GET   
* Request header: None   

A sample curl request would be:   

```
curl -X GET \   
  --url 'http://localhost:8080/caesar/api/v1.0/job/f135bcee-562b-4f01-ad9b-103c35b13b36/status'   
```

Server response is:   

```
{
  "elapsed_time": "27.3435878754",
  "exit_status": 0,
  "job_id": "f135bcee-562b-4f01-ad9b-103c35b13b36",
  "pid": "11539",
  "state": "SUCCESS",
  "status": "Process terminated with success"
}
```

Exit status is the shell exit status of background task executed and pid the corresponding process id. Possible job states are: {STARTED, TIMED-OUT, ABORTED, RUNNING, SUCCESS, FAILURE}. 


### **Get job output**
* URL:```http://server-address:port/caesar/api/v1.0/job/[job_id]/output```   
* Request methods: GET   
* Request header: None   

A sample curl request would be:   

```
curl -X GET \   
  --fail -o job_output.tar.gz \
  --url 'http://localhost:8080/caesar/api/v1.0/job/c3c9348a-bea0-4141-8fe9-7f64076a2327/output'   
```

The response is a tar.gz file containing all job directory files (logs, output data, run scripts, etc).  

### **Cancel job**
* URL:```http://server-address:port/caesar/api/v1.0/job/[job_id]/cancel```   
* Request methods: POST   
* Request header: None  

### **Get job ids**
* URL:```http://server-address:port/caesar/api/v1.0/jobs```   
* Request methods: GET   
* Request header: None  
