# Job monitoring service

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 971–1005). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

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


