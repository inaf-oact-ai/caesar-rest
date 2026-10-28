# Celery deployment — legacy

> **Legacy / deprecated backend:** Celery is retained for historical reference. Slurm is the actively developed deployment mode.

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 167–251). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

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

