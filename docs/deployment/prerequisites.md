# Deployment prerequisites and shared services

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 134–166). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

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

