# Web application CLI options

> For the current complete option set, check `apps/run_app.py --help`; the list below is an unmodified historical reference.

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 285–378). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

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

