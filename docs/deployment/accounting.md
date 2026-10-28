# Accounting service

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 1143–1163). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

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


