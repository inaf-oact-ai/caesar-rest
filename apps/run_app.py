from __future__ import print_function

############################################################
#              MODULE IMPORTS
############################################################
# - Standard modules
import os
import sys
import json
import time
import datetime
import numpy as np
import argparse

import structlog
import logging

# - caesar_rest modules
import caesar_rest
from caesar_rest import __version__, __date__
from caesar_rest import logger
from caesar_rest.config import Config
## from caesar_rest.data_manager import DataManager  ### DEPRECATED
from caesar_rest.job_configurator import JobConfigurator
from caesar_rest.app import create_app
from caesar_rest import oidc
from caesar_rest import mongo
from caesar_rest import celery
from caesar_rest import jobmgr_kube
from caesar_rest import jobmgr_slurm

#### GET SCRIPT ARGS ####
def str2bool(v):
	if v.lower() in ('yes', 'true', 't', 'y', '1'):
		return True
	elif v.lower() in ('no', 'false', 'f', 'n', '0'):
		return False
	else:
		raise argparse.ArgumentTypeError('Boolean value expected.')

###########################
##     ARGS
###########################
def get_args():
	"""This function parses and return arguments passed in"""
	parser = argparse.ArgumentParser(description="Parse args.")

	# - Specify cmd options
	parser.add_argument('-datadir','--datadir', dest='datadir', default='/opt/caesar-rest/data', required=False, type=str, help='Directory where to store uploaded data') 
	parser.add_argument('-jobdir','--jobdir', dest='jobdir', default='/opt/caesar-rest/jobs', required=False, type=str, help='Directory where to store jobs') 
	parser.add_argument('-modeldir','--modeldir', dest='modeldir', default='/opt/caesar-rest/models', required=False, type=str, help='Directory where models are stored') 
	parser.add_argument('-job_scheduler','--job_scheduler', dest='job_scheduler', default='slurm', required=False, type=str, help='Job scheduler to be used. Options are: {celery, kubernetes, slurm} (default=slurm)')
	parser.add_argument('-job_monitoring_period','--job_monitoring_period', dest='job_monitoring_period', default=5, required=False, type=int, help='Job monitoring poll period in seconds') 
	parser.add_argument('--debug', dest='debug', action='store_true')	
	parser.set_defaults(debug=True)

	# - Log options
	parser.add_argument('-loglevel','--loglevel', dest='loglevel', default='INFO', required=False, type=str, help='Log level to be used (default=INFO)')
	parser.add_argument('--logtofile', dest='logtofile', action='store_true')	
	parser.set_defaults(logtofile=False)
	parser.add_argument('-logdir','--logdir', dest='logdir', default='/opt/caesar-rest/logs', required=False, type=str, help='Directory where to store logs')
	parser.add_argument('-logfile','--logfile', dest='logfile', default='app_logs.json', required=False, type=str, help='Name of json log file')
	parser.add_argument('-logfile_maxsize','--logfile_maxsize', dest='logfile_maxsize', default=5.0, required=False, type=float, help='Max file size in MB (default=5)')


	# - AAI options
	parser.add_argument('--aai', dest='aai', action='store_true')	
	parser.set_defaults(aai=False)	
	parser.add_argument('-secretfile','--secretfile', dest='secretfile', default='config/client_secrets.json', required=False, type=str, help='File (.json) with client credentials for AAI')
	parser.add_argument('-openid_realm','--openid_realm', dest='openid_realm', default='neanias-development', required=False, type=str, help='OpenID realm used in AAI (defaul=neanias-development)') 
	parser.add_argument('--ssl', dest='ssl', action='store_true')	
	parser.set_defaults(ssl=False)
	
	# - Algorithm options
	parser.add_argument('-mrcnn_weights','--mrcnn_weights', dest='mrcnn_weights', default='/opt/Software/MaskR-CNN/install/share/mrcnn_weights.h5', required=False, type=str, help='File (.h5) with network weights used in Mask-RCNN app')

	# - DB options
	parser.add_argument('--no-db', dest='db', action='store_false')
	parser.add_argument('--db', dest='db', action='store_true')	
	parser.set_defaults(db=True)
	parser.add_argument('-dbhost','--dbhost', dest='dbhost', default='localhost', required=False, type=str, help='Host of MongoDB database (default=localhost)')
	parser.add_argument('-dbname','--dbname', dest='dbname', default='caesardb', required=False, type=str, help='Name of MongoDB database (default=caesardb)')
	parser.add_argument('-dbport','--dbport', dest='dbport', default=27017, required=False, type=int, help='Port of MongoDB database (default=27017)')

	# - Celery options
	parser.add_argument('-result_backend_host','--result_backend_host', dest='result_backend_host', default='localhost', required=False, type=str, help='Host of Celery result backend (default=localhost)')
	parser.add_argument('-result_backend_port','--result_backend_port', dest='result_backend_port', default=6379, required=False, type=int, help='Port of Celery result backend (default=6379)')
	parser.add_argument('-result_backend_proto','--result_backend_proto', dest='result_backend_proto', default='redis', required=False, type=str, help='Celery result backend type (default=redis)')
	parser.add_argument('-result_backend_user','--result_backend_user', dest='result_backend_user', default='', required=False, type=str, help='Celery result backend username (default=empty)')
	parser.add_argument('-result_backend_pass','--result_backend_pass', dest='result_backend_pass', default='', required=False, type=str, help='Celery result backend password (default=empty)')
	parser.add_argument('-result_backend_dbname','--result_backend_dbname', dest='result_backend_dbname', default='0', required=False, type=str, help='Celery result backend database name (default=empty)')

	parser.add_argument('-broker_host','--broker_host', dest='broker_host', default='localhost', required=False, type=str, help='Host of Celery broker (default=localhost)')
	parser.add_argument('-broker_port','--broker_port', dest='broker_port', default=5672, required=False, type=int, help='Port of Celery broker (default=5672)')
	parser.add_argument('-broker_proto','--broker_proto', dest='broker_proto', default='amqp', required=False, type=str, help='Protocol of Celery broker (default=amqp)')
	parser.add_argument('-broker_user','--broker_user', dest='broker_user', default='guest', required=False, type=str, help='Username used in Celery broker (default=guest)')
	parser.add_argument('-broker_pass','--broker_pass', dest='broker_pass', default='guest', required=False, type=str, help='Password used in Celery broker (default=guest)')

	# - Kubernetes scheduler options
	parser.add_argument('--kube_incluster', dest='kube_incluster', action='store_true')	
	parser.set_defaults(kube_incluster=False)
	parser.add_argument('-kube_config','--kube_config', dest='kube_config', default='', required=False, type=str, help='Kube configuration file path (default=search in standard path)')
	parser.add_argument('-kube_cafile','--kube_cafile', dest='kube_cafile', default='', required=False, type=str, help='Kube certificate authority file path')
	parser.add_argument('-kube_keyfile','--kube_keyfile', dest='kube_keyfile', default='', required=False, type=str, help='Kube private key file path')
	parser.add_argument('-kube_certfile','--kube_certfile', dest='kube_certfile', default='', required=False, type=str, help='Kube certificate file path')
	
	# - Slurm scheduler options
	parser.add_argument('-slurm_keyfile','--slurm_keyfile', dest='slurm_keyfile', default='', required=False, type=str, help='Slurm rest service private key file path')
	parser.add_argument('-slurm_user','--slurm_user', dest='slurm_user', default='cirasa', required=False, type=str, help='Username enabled to run in Slurm cluster')
	parser.add_argument('-slurm_host','--slurm_host', dest='slurm_host', default='localhost', required=False, type=str, help='Slurm cluster host/ipaddress')
	parser.add_argument('-slurm_port','--slurm_port', dest='slurm_port', default=6820, required=False, type=int, help='Slurm rest service port')
	parser.add_argument('-slurm_batch_workdir','--slurm_batch_workdir', dest='slurm_batch_workdir', default='/opt/slurm/batchlogs/caesar-rest', required=False, type=str, help='Cluster directory where to place Slurm batch logs (must be writable by slurm_user)')
	parser.add_argument('-slurm_queue','--slurm_queue', dest='slurm_queue', default='normal', required=False, type=str, help='Slurm cluster queue for submitting jobs')
	parser.add_argument('-slurm_jobdir','--slurm_jobdir', dest='slurm_jobdir', default='/mnt/storage/jobs', required=False, type=str, help='Path at which the job directory is mounted in Slurm cluster')	
	parser.add_argument('-slurm_datadir','--slurm_datadir', dest='slurm_datadir', default='/mnt/storage/data', required=False, type=str, help='Path at which the data directory is mounted in Slurm cluster')	
	parser.add_argument('-slurm_modeldir','--slurm_modeldir', dest='slurm_modeldir', default='/mnt/storage/models', required=False, type=str, help='Path at which the models directory is mounted in Slurm cluster')	
	parser.add_argument('-slurm_max_cores_per_job','--slurm_max_cores_per_job', dest='slurm_max_cores_per_job', default=4, required=False, type=int, help='Slurm maximum number of cores reserved for a job (default=4)')
	
	# - Volume mount options
	parser.add_argument('--mount_rclone_volume', dest='mount_rclone_volume', action='store_true')	
	parser.set_defaults(mount_rclone_volume=False)
	parser.add_argument('-mount_volume_path','--mount_volume_path', dest='mount_volume_path', default='/mnt/storage', required=False, type=str, help='Mount volume path for container jobs')
	parser.add_argument('-rclone_storage_name','--rclone_storage_name', dest='rclone_storage_name', default='neanias-nextcloud', required=False, type=str, help='rclone remote storage name (default=neanias-nextcloud)')
	parser.add_argument('-rclone_storage_path','--rclone_storage_path', dest='rclone_storage_path', default='.', required=False, type=str, help='rclone remote storage path (default=.)')
	
	# - Singularity container app options
	parser.add_argument(
		'-caesar_container',
		'--caesar_container', 
		dest='caesar_container', 
		default='/opt/containers/caesar/caesar-job_latest.sif', 
		required=False, 
		type=str, 
		help='Path to caesar job Singularity container (default=/opt/containers/caesar/caesar-job_latest.sif)'
	)
	
	parser.add_argument(
		'-aegean_container',
		'--aegean_container', 
		dest='aegean_container', 
		default='/opt/containers/aegean/aegean-job_latest.sif', 
		required=False, 
		type=str, 
		help='Path to aegean job Singularity container (default=/opt/containers/aegean/aegean-job_latest.sif)'
	)
	
	parser.add_argument(
		'-cutex_container',
		'--cutex_container', 
		dest='cutex_container', 
		default='/opt/containers/cutex/cutex-job_latest.sif', 
		required=False, 
		type=str, 
		help='Path to cutex job Singularity container (default=/opt/containers/cutex/cutex-job_latest.sif)'
	)
	
	parser.add_argument(
		'-mrcnn_container',
		'--mrcnn_container', 
		dest='mrcnn_container', 
		default='/opt/containers/mrcnn/mrcnn-detect_latest.sif', 
		required=False, 
		type=str, 
		help='Path to caesar-mrcnn job Singularity container (default=/opt/containers/mrcnn/mrcnn-detect_latest.sif)'
	)
	
	parser.add_argument(
		'-cnn_classifier_container',
		'--cnn_classifier_container', 
		dest='cnn_classifier_container', 
		default='/opt/containers/sclassifier/cnn-classifier_latest.sif', 
		required=False, 
		type=str, 
		help='Path to CNN classifier Singularity container (default=/opt/containers/sclassifier/cnn-classifier_latest.sif)'
	)
	
	parser.add_argument(
		'-vit_classifier_container',
		'--vit_classifier_container', 
		dest='vit_classifier_container', 
		default='/opt/containers/sclassifier-vit/vit-classifier_latest.sif', 
		required=False, 
		type=str, 
		help='Path to VIT classifier Singularity container (default=/opt/containers/sclassifier/cnn-classifier_latest.sif)'
	)
	
	parser.add_argument(
		'-umap_container',
		'--umap_container', 
		dest='umap_container', 
		default='/opt/containers/sclassifier/umap_latest.sif', 
		required=False, 
		type=str, 
		help='Path to UMAP Singularity container (default=/opt/containers/sclassifier/umap_latest.sif)'
	)
	
	parser.add_argument(
		'-outlier_finder_container',
		'--outlier_finder_container', 
		dest='outlier_finder_container', 
		default='/opt/containers/sclassifier/outlier_finder_latest.sif', 
		required=False, 
		type=str, 
		help='Path to OutlierFinder Singularity container (default=/opt/containers/sclassifier/outlier_finder_latest.sif)'
	)
	
	parser.add_argument(
		'-hdbscan_container',
		'--hdbscan_container', 
		dest='hdbscan_container', 
		default='/opt/containers/sclassifier/hdbscan_latest.sif', 
		required=False, 
		type=str, 
		help='Path to HDBSCAN Singularity container (default=/opt/containers/sclassifier/hdbscan_latest.sif)'
	)
	
	parser.add_argument(
		'-simsearch_container',
		'--simsearch_container', 
		dest='simsearch_container', 
		default='/opt/containers/sclassifier/similarity-search_latest.sif', 
		required=False, 
		type=str, 
		help='Path to Similarity Search Singularity container (default=/opt/containers/sclassifier/similarity-search_latest.sif)'
	)
	
	parser.add_argument(
		'-caesar_yolo_container',
		'--caesar_yolo_container', 
		dest='caesar_yolo_container', 
		default='/opt/containers/caesar-yolo/caesar-yolo-job_latest.sif', 
		required=False, 
		type=str, 
		help='Path to CAESAR-YOLO Singularity container (default=/opt/containers/caesar-yolo/caesar-yolo-job_latest.sif)'
	)
	
	parser.add_argument(
		'-sfforecaster_container',
		'--sfforecaster_container', 
		dest='sfforecaster_container', 
		default='/opt/containers/sfforecaster/sfforecaster-job_latest.sif', 
		required=False, 
		type=str, 
		help='Path to Solar Flare Forecaster Singularity container (default=/opt/containers/sfforecaster/sfforecaster-job_latest.sif)'
	)
	
	parser.add_argument(
		'-fextractor_tf_container', 
		'--fextractor_tf_container', 
		dest='fextractor_tf_container', 
		default='/opt/containers/fextractor/fextractor-tf_latest.sif', 
		required=False, 
		type=str, 
		help='Path to TensorFlow fextractor Singularity container'
	)
	
	parser.add_argument(
		'-fextractor_torch_container', 
		'--fextractor_torch_container', 
		dest='fextractor_torch_container', 
		default='/opt/containers/fextractor/fextractor-torch_latest.sif', 
		required=False, 
		type=str, 
		help='Path to PyTorch fextractor Singularity container'
	)
	
	parser.add_argument(
		'-fextractor_chronos_container', 
		'--fextractor_chronos_container', 
		dest='fextractor_chronos_container', 
		default='/opt/containers/fextractor/fextractor-chronos_latest.sif', 
		required=False, 
		type=str, 
		help='Path to Chronos fextractor Singularity container'
	)
	
	parser.add_argument(
		'-fextractor_moirai_container', 
		'--fextractor_moirai_container', 
		dest='fextractor_moirai_container', 
		default='/opt/containers/fextractor/fextractor-moirai_latest.sif', 
		required=False, 
		type=str, 
		help='Path to Moirai fextractor Singularity container'
	)
	
	parser.add_argument(
		'-fextractor_fats_container', 
		'--fextractor_fats_container', 
		dest='fextractor_fats_container', 
		default='/opt/containers/fextractor/fextractor-fats_latest.sif', 
		required=False, 
		type=str, 
		help='Path to FATS fextractor Singularity container'
	)
	
	parser.add_argument(
		'-fextractor_licu_container', 
		'--fextractor_licu_container', 
		dest='fextractor_licu_container', 
		default='/opt/containers/fextractor/fextractor-licu_latest.sif', 
		required=False, 
		type=str, 
		help='Path to LightCurve (LICU) fextractor Singularity container'
	)
	
	parser.add_argument(
		'-fextractor_falcon_container', 
		'--fextractor_falcon_container', 
		dest='fextractor_falcon_container', 
		default='/opt/containers/fextractor/fextractor-falcon_latest.sif', 
		required=False, 
		type=str, 
		help='Path to Falcon1 fextractor Singularity container'
	)
	
	parser.add_argument(
		'-oxkat_container',
		'--oxkat_container', 
		dest='oxkat_container', 
		default='/opt/containers/oxkat/oxkat-caesar.sif', 
		required=False, 
		type=str, 
		help='Path to OxKAT Singularity container (default=/opt/containers/oxkat/oxkat-caesar.sif)'
	)
	
	# - Generic staged pipeline execution options
	parser.add_argument(
		'--pipeline_staged_execution_enabled',
		dest='pipeline_staged_execution_enabled',
		action='store_true',
		help='Enable staged pipeline execution through Slurm'
	)

	parser.add_argument(
		'--pipeline_staged_applications',
		dest='pipeline_staged_applications',
		default='oxkat',
		type=str,
		help='Comma-separated applications allowed for staged pipeline execution (default=oxkat)'
	)

	parser.add_argument(
		'--pipeline_python_executable',
		dest='pipeline_python_executable',
		default='/usr/bin/python3',
		type=str,
		help='Absolute path to the Python interpreter available on Slurm compute nodes'
	)
	
	# - Pipeline artifact retention options
	parser.add_argument(
		'--pipeline_artifact_retention_root',
		dest='pipeline_artifact_retention_root',
		default='',
		type=str,
		help='Absolute directory for retained pipeline artifacts (empty disables retention)'
	)

	parser.add_argument(
		'--pipeline_artifact_retention_max_file_bytes',
		dest='pipeline_artifact_retention_max_file_bytes',
		default=1024 * 1024 * 1024,
		type=int,
		help='Maximum size in bytes of each retained artifact (default: 1 GiB)'
	)
	
	parser.add_argument(
		'--pipeline_artifact_retention_max_directory_bytes',
		dest='pipeline_artifact_retention_max_directory_bytes',
		default=1024 * 1024 * 1024 * 1024,
		type=int,
		help='Maximum total size in bytes of a retained directory artifact (default: 1 TiB)'
	)

	parser.add_argument(
		'--pipeline_artifact_retention_max_directory_entries',
		dest='pipeline_artifact_retention_max_directory_entries',
		default=100000,
		type=int,
		help='Maximum number of files and subdirectories per retained directory artifact'
	)

	parser.add_argument(
		'--pipeline_artifact_retention_max_directory_depth',
		dest='pipeline_artifact_retention_max_directory_depth',
		default=16,
		type=int,
		help='Maximum nesting depth of a retained directory artifact'
	)	
	
	parser.add_argument(
		'--pipeline_artifact_retention_root_cluster',
		dest='pipeline_artifact_retention_root_cluster',
		default='',
		type=str,
		help='Slurm-visible root for retained pipeline artifacts (V2)'
	)

	parser.add_argument(
		'--pipeline_v2_applications',
		dest='pipeline_v2_applications',
		default='{}',
		type=str,
		help='JSON object defining V2 application policies'
	)	
	
	# - Dynamic dataset registry options
	parser.add_argument(
		'--dataset_registry_enabled',
		dest='dataset_registry_enabled',
		action='store_true',
		help='Enable MongoDB-backed dynamic dataset registry'
	)

	parser.add_argument(
		'--dataset_allowed_roots',
		dest='dataset_allowed_roots',
		default='',
		type=str,
		help='Comma-separated absolute directory paths permitted for registered datasets'
	)

	parser.add_argument(
		'--dataset_admin_identities',
		dest='dataset_admin_identities',
		default='',
		type=str,
		help='Comma-separated administrator OIDC identities (issuer|subject)'
	)

	# - Legacy Dataset options
	parser.add_argument('-dataset_smgps','--dataset_smgps', dest='dataset_smgps', default='', required=False, type=str, help='Path to smgps dataset json filelist')
	parser.add_argument('-dataset_smgps_feats_simclr','--dataset_smgps_feats_simclr', dest='dataset_smgps_feats_simclr', default='', required=False, type=str, help='Path to smgps_feats_simclr dataset json filelist')
	parser.add_argument('-dataset_smgps_feats_siglip','--dataset_smgps_feats_siglip', dest='dataset_smgps_feats_siglip', default='', required=False, type=str, help='Path to smgps_feats_siglip dataset json filelist')
	parser.add_argument('-dataset_smgps_feats_dinov2','--dataset_smgps_feats_dinov2', dest='dataset_smgps_feats_dinov2', default='', required=False, type=str, help='Path to smgps_feats_dinov2 dataset json filelist')
	parser.add_argument('-dataset_emu_pilot','--dataset_emu_pilot', dest='dataset_emu_pilot', default='', required=False, type=str, help='Path to emu-pilot dataset json filelist')
	parser.add_argument('-dataset_emu','--dataset_emu', dest='dataset_emu', default='', required=False, type=str, help='Path to emu dataset json filelist')
	parser.add_argument('-dataset_emu_scorpio_pilot','--dataset_emu_scorpio_pilot', dest='dataset_emu_scorpio_pilot', default='', required=False, type=str, help='Path to emu-scorpio-pilot dataset json filelist')
	parser.add_argument('-dataset_emu_gp_pilot','--dataset_emu_gp_pilot', dest='dataset_emu_gp_pilot', default='', required=False, type=str, help='Path to emu-gp-pilot dataset json filelist')
	
	args = parser.parse_args()	

	return args


#===========================
#==   PARSE ARGS
#===========================
logger.info("Parsing cmd line arguments ...")
try:
	args= get_args()
except Exception as ex:
	logger.error("Failed to get and parse options (err=%s)",str(ex))
	sys.exit(1)

# - Dir options
datadir= args.datadir
jobdir= args.jobdir
modeldir= args.modeldir
debug= args.debug

# - Log level options
loglevel= args.loglevel
logtofile= args.logtofile
logdir= args.logdir
logfile= args.logfile
logfilepath= os.path.join(logdir,logfile)
logfile_maxsize= args.logfile_maxsize

if logtofile:
	logger.info("Enabling logging to file %s ..." % logfilepath)
	
	formatter_file= structlog.stdlib.ProcessorFormatter(
		processor=structlog.processors.JSONRenderer(),
	)

	try:
		handler_file= logging.handlers.RotatingFileHandler(
			logfilepath, 
			maxBytes=logfile_maxsize*1024*1024,
			backupCount=2 
		)
	except Exception as e:
		logger.error("Failed to initialize file logger (err=%s)!" % str(e))
		sys.exit(1)

	handler_file.setFormatter(formatter_file)
	logger.addHandler(handler_file)

logger.info("Setting log level to %s ..." % loglevel)
logger.setLevel(loglevel)

# - AAI options
use_aai= args.aai
secret_file= args.secretfile
openid_realm= args.openid_realm
ssl= args.ssl

# - App options
job_monitoring_period= args.job_monitoring_period
mrcnn_weights= args.mrcnn_weights

# - Scheduler options
job_scheduler= args.job_scheduler
if job_scheduler!='celery' and job_scheduler!='kubernetes' and job_scheduler!='slurm':
	logger.error("Unsupported job scheduler (hint: supported are {celery,kubernetes,slurm})!")
	sys.exit(1)

if job_scheduler=='kubernetes' and jobmgr_kube is None:
	logger.error("Chosen scheduler is Kubernetes but kube client failed to be instantiated (see previous logs)!")
	sys.exit(1)

# - DB & celery result backend options
use_db= args.db
dbhost= 'mongodb://' + args.dbhost + ':' + str(args.dbport) + '/' + args.dbname

if use_db:
	logger.info("Using db url: %s" % dbhost)
else:
	logger.warn("DB usage is disabled...")

result_backend_host= args.result_backend_host
result_backend_port= args.result_backend_port
result_backend_proto= args.result_backend_proto
result_backend_user= args.result_backend_user
result_backend_pass= args.result_backend_pass
result_backend_dbname= args.result_backend_dbname

result_backend= ''
if result_backend_proto=='redis':	
	result_backend= result_backend_proto + '://' + result_backend_host + ':' + str(result_backend_port) + '/' + result_backend_dbname
elif result_backend_proto=='mongodb':
	result_backend= result_backend_proto + '://' + result_backend_host + ':' + str(result_backend_port) + '/' + result_backend_dbname
else:
	logger.error("Unsupported result backend (hint: supported are {redis,mongodb})!")
	sys.exit(1)

if job_scheduler=='celery':
	logger.info("Using result_backend: %s" % result_backend)


# - Celery broker options
broker_host= args.broker_host
broker_port= args.broker_port
broker_proto= args.broker_proto
broker_user= args.broker_user
broker_pass= args.broker_pass 
broker_url= broker_proto + '://' + broker_user + ':' + broker_pass + '@' + broker_host + ':' + str(broker_port) + '/'

if job_scheduler=='celery':
	logger.info("Using broker_url: %s" % broker_url)


# - Kubernetes options
kube_incluster= args.kube_incluster
kube_config= args.kube_config
kube_certfile= args.kube_certfile
kube_keyfile= args.kube_keyfile
kube_cafile= args.kube_cafile

# - Slurm options
slurm_keyfile= args.slurm_keyfile
slurm_user= args.slurm_user
slurm_host= args.slurm_host
slurm_port= args.slurm_port
slurm_batch_workdir= args.slurm_batch_workdir
slurm_queue= args.slurm_queue
slurm_jobdir= args.slurm_jobdir
slurm_datadir= args.slurm_datadir
slurm_modeldir= args.slurm_modeldir
slurm_max_cores_per_job= args.slurm_max_cores_per_job

# - Singularity container options
caesar_container= args.caesar_container
aegean_container= args.aegean_container
cutex_container= args.cutex_container
mrcnn_container= args.mrcnn_container
cnn_classifier_container= args.cnn_classifier_container
vit_classifier_container= args.vit_classifier_container	
umap_container= args.umap_container
outlier_finder_container= args.outlier_finder_container
hdbscan_container= args.hdbscan_container
simsearch_container= args.simsearch_container
caesar_yolo_container= args.caesar_yolo_container
sfforecaster_container= args.sfforecaster_container
fextractor_tf_container= args.fextractor_tf_container
fextractor_torch_container= args.fextractor_torch_container
fextractor_chronos_container= args.fextractor_chronos_container
fextractor_moirai_container= args.fextractor_moirai_container
fextractor_fats_container= args.fextractor_fats_container
fextractor_licu_container= args.fextractor_licu_container
fextractor_falcon_container= args.fextractor_falcon_container
oxkat_container= args.oxkat_container

# - Legacy dataset options
dataset_smgps= args.dataset_smgps
dataset_smgps_feats_simclr= args.dataset_smgps_feats_simclr
dataset_smgps_feats_siglip= args.dataset_smgps_feats_siglip
dataset_smgps_feats_dinov2= args.dataset_smgps_feats_dinov2
dataset_emu_pilot= args.dataset_emu_pilot
dataset_emu= args.dataset_emu
dataset_emu_scorpio_pilot= args.dataset_emu_scorpio_pilot
dataset_emu_gp_pilot= args.dataset_emu_gp_pilot

# - Generic staged pipeline execution options
pipeline_staged_execution_enabled = args.pipeline_staged_execution_enabled

pipeline_staged_applications = tuple(
	name.strip().lower()
	for name in args.pipeline_staged_applications.split(',')
	if name.strip()
)

pipeline_python_executable = args.pipeline_python_executable


# - Validate staged execution configuration
if pipeline_staged_execution_enabled:
	if job_scheduler != 'slurm':
		logger.error("Staged pipeline execution requires the Slurm scheduler")
		sys.exit(1)

	if not args.dataset_registry_enabled:
		logger.error("Staged pipeline execution requires the dynamic dataset registry")
		sys.exit(1)

	if not pipeline_staged_applications:
		logger.error("No staged pipeline applications configured")
		sys.exit(1)

	if (
		not os.path.isabs(pipeline_python_executable)
		or os.path.normpath(pipeline_python_executable) != pipeline_python_executable
	):
		logger.error("Pipeline Python executable must be a normalized absolute path")
		sys.exit(1)
		
# - Pipeline artifact retention options
pipeline_artifact_retention_root = args.pipeline_artifact_retention_root.strip()
pipeline_artifact_retention_max_file_bytes = args.pipeline_artifact_retention_max_file_bytes
pipeline_artifact_retention_max_directory_bytes = args.pipeline_artifact_retention_max_directory_bytes
pipeline_artifact_retention_max_directory_entries = args.pipeline_artifact_retention_max_directory_entries
pipeline_artifact_retention_max_directory_depth = args.pipeline_artifact_retention_max_directory_depth
pipeline_artifact_retention_root_cluster = args.pipeline_artifact_retention_root_cluster.strip()

try:
	pipeline_v2_applications = json.loads(args.pipeline_v2_applications)
except (ValueError, TypeError):
	logger.error("Invalid pipeline V2 application policy JSON")
	sys.exit(1)

		
# - Validate retention configuration
if pipeline_artifact_retention_root:
	if (
		not os.path.isabs(pipeline_artifact_retention_root)
		or os.path.normpath(pipeline_artifact_retention_root)
		!= pipeline_artifact_retention_root
	):
		logger.error(
			"Pipeline artifact retention root must be a normalized absolute path"
		)
		sys.exit(1)

if pipeline_artifact_retention_max_file_bytes <= 0:
	logger.error(
		"Pipeline artifact retention maximum file size must be positive"
	)
	sys.exit(1)		
		
if (
	pipeline_artifact_retention_max_directory_bytes <= 0
	or pipeline_artifact_retention_max_directory_entries <= 0
	or pipeline_artifact_retention_max_directory_depth <= 0
):
	logger.error(
		"Pipeline artifact retention directory limits must be positive"
	)
	sys.exit(1)

	
if pipeline_artifact_retention_root_cluster:
	if (
		not os.path.isabs(pipeline_artifact_retention_root_cluster)
		or os.path.normpath(pipeline_artifact_retention_root_cluster)
		!= pipeline_artifact_retention_root_cluster
		or pipeline_artifact_retention_root_cluster == '/'
	):
		logger.error("Invalid cluster artifact retention root")
		sys.exit(1)
	
if not isinstance(pipeline_v2_applications, dict):
	logger.error("V2 application policies must be a JSON object")
	sys.exit(1)

if pipeline_v2_applications:
	if not pipeline_staged_execution_enabled:
		logger.error("V2 requires staged execution to be enabled")
		sys.exit(1)

	if not pipeline_artifact_retention_root:
		logger.error("V2 requires an application artifact retention root")
		sys.exit(1)

	if not pipeline_artifact_retention_root_cluster:
		logger.error("V2 requires a cluster artifact retention root")
		sys.exit(1)

		
# - Dynamic dataset registry options
dataset_registry_enabled = args.dataset_registry_enabled

dataset_allowed_roots = [
	os.path.realpath(path.strip())
	for path in args.dataset_allowed_roots.split(',')
	if path.strip()
]


dataset_admin_identities = [
	identity.strip().replace(r'\|', '|')
	for identity in args.dataset_admin_identities.split(',')
	if identity.strip()
]
logger.info("Parsed dataset admin identities: %r", dataset_admin_identities)

# - Validate administrator identities.
for identity in dataset_admin_identities:
	if '|' not in identity:
		logger.error("Invalid dataset administrator identity: expected issuer|subject")
		sys.exit(1)

# - Validate storage roots.
for path in dataset_allowed_roots:
	if not os.path.isdir(path):
		logger.error("Dataset storage root does not exist or is not a directory: %s", path)
		sys.exit(1)

# - Registry requires AAI and MongoDB.
if dataset_registry_enabled:
	if not use_aai or oidc is None:
		logger.error("Dynamic dataset registry requires AAI")
		sys.exit(1)

	if not use_db or mongo is None:
		logger.error("Dynamic dataset registry requires MongoDB")
		sys.exit(1)

	if not dataset_allowed_roots:
		logger.error("Dynamic dataset registry requires allowed storage roots")
		sys.exit(1)

	if not dataset_admin_identities:
		logger.error("Dynamic dataset registry requires administrator identities")
		sys.exit(1)

#===============================
#==   INIT
#===============================
# - Create config class
logger.info("Creating app configuration ...")
config= Config()
config.UPLOAD_FOLDER= datadir
config.JOB_DIR= jobdir
config.MODEL_DIR= modeldir
config.USE_AAI= False
config.JOB_MONITORING_PERIOD= job_monitoring_period

if use_aai and oidc is not None:
	config.USE_AAI= True
	config.SECRET_KEY= 'SomethingNotEntirelySecret'
	config.OIDC_CLIENT_SECRETS= secret_file
	config.OIDC_OPENID_REALM= openid_realm
	config.OIDC_TOKEN_TYPE_HINT = 'access_token'


if use_db and mongo is not None:
	config.MONGO_HOST= args.dbhost
	config.MONGO_PORT= args.dbport
	config.MONGO_DBNAME= args.dbname
	config.MONGO_URI= dbhost
	config.USE_MONGO= True

config.MASKRCNN_WEIGHTS = mrcnn_weights

config.JOB_SCHEDULER= job_scheduler
config.KUBE_CONFIG_PATH= kube_config
config.KUBE_INCLUSTER= kube_incluster
config.KUBE_CERTFILE= kube_certfile
config.KUBE_KEYFILE= kube_keyfile
config.KUBE_CERTAUTHFILE= kube_cafile

config.SLURM_KEYFILE= slurm_keyfile
config.SLURM_QUEUE= slurm_queue
config.SLURM_USER= slurm_user
config.SLURM_HOST= slurm_host
config.SLURM_BATCH_WORKDIR= slurm_batch_workdir
config.SLURM_PORT= slurm_port
config.SLURM_JOB_DIR= slurm_jobdir
config.SLURM_DATA_DIR= slurm_datadir
config.SLURM_MODEL_DIR= slurm_modeldir
config.SLURM_MAX_CORE_PER_JOB= slurm_max_cores_per_job

config.MOUNT_RCLONE_VOLUME= args.mount_rclone_volume
config.MOUNT_VOLUME_PATH= args.mount_volume_path
config.RCLONE_REMOTE_STORAGE= args.rclone_storage_name
config.RCLONE_REMOTE_STORAGE_PATH= args.rclone_storage_path

config.LOG_TO_FILE= logtofile
config.LOG_LEVEL= loglevel
config.LOG_DIR= logdir
config.LOG_FILE= logfile
	
config.SLURM_CAESAR_JOB_IMAGE= caesar_container
config.SLURM_AEGEAN_JOB_IMAGE= aegean_container
config.SLURM_CUTEX_JOB_IMAGE= cutex_container
config.SLURM_MASKRCNN_JOB_IMAGE= mrcnn_container
config.SLURM_CNN_CLASSIFIER_JOB_IMAGE= cnn_classifier_container
config.SLURM_VIT_CLASSIFIER_JOB_IMAGE= vit_classifier_container
config.SLURM_UMAP_JOB_IMAGE= umap_container
config.SLURM_OUTLIER_FINDER_JOB_IMAGE= outlier_finder_container
config.SLURM_HDBSCAN_JOB_IMAGE= hdbscan_container
config.SLURM_SIMSEARCH_JOB_IMAGE= simsearch_container
config.SLURM_CAESAR_YOLO_JOB_IMAGE= caesar_yolo_container
config.SLURM_SFFORECASTER_JOB_IMAGE= sfforecaster_container
config.SLURM_FEXTRACTOR_TF_JOB_IMAGE= fextractor_tf_container
config.SLURM_FEXTRACTOR_TORCH_JOB_IMAGE= fextractor_torch_container
config.SLURM_FEXTRACTOR_CHRONOS_JOB_IMAGE= fextractor_chronos_container
config.SLURM_FEXTRACTOR_MOIRAI_JOB_IMAGE= fextractor_moirai_container
config.SLURM_FEXTRACTOR_FATS_JOB_IMAGE= fextractor_fats_container
config.SLURM_FEXTRACTOR_LICU_JOB_IMAGE= fextractor_licu_container
config.SLURM_FEXTRACTOR_FALCON_JOB_IMAGE= fextractor_falcon_container
config.SLURM_OXKAT_JOB_IMAGE= oxkat_container

# - Generic staged pipeline execution
config.PIPELINE_STAGED_EXECUTION_ENABLED = pipeline_staged_execution_enabled
config.PIPELINE_STAGED_APPLICATIONS = pipeline_staged_applications
config.PIPELINE_PYTHON_EXECUTABLE = pipeline_python_executable
config.PIPELINE_ARTIFACT_RETENTION_ROOT = pipeline_artifact_retention_root
config.PIPELINE_ARTIFACT_RETENTION_MAX_FILE_BYTES = pipeline_artifact_retention_max_file_bytes
config.PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES = pipeline_artifact_retention_max_directory_bytes
config.PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES = pipeline_artifact_retention_max_directory_entries
config.PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH = pipeline_artifact_retention_max_directory_depth
config.PIPELINE_ARTIFACT_RETENTION_ROOT_CLUSTER = pipeline_artifact_retention_root_cluster
config.PIPELINE_V2_APPLICATIONS = pipeline_v2_applications

# - Create job configurator
logger.info("Creating job configurator ...")
jobcfg= JobConfigurator()

# - Configure the Celery broker and result backend only when selected.
if job_scheduler == 'celery':
	from caesar_rest.backend_dependencies import require_celery_app

	celery_app = require_celery_app()
	celery_app.conf.result_backend = result_backend
	celery_app.conf.broker_url = broker_url

# - Set legacy dataset configs
config.DATASETS["smgps"]["path"]= dataset_smgps
config.DATASETS["smgps-feats-simclr"]["path"]= dataset_smgps_feats_simclr
config.DATASETS["smgps-feats-siglip"]["path"]= dataset_smgps_feats_siglip
config.DATASETS["smgps-feats-dinov2"]["path"]= dataset_smgps_feats_dinov2
config.DATASETS["emu-pilot"]["path"]= dataset_emu_pilot
config.DATASETS["emu"]["path"]= dataset_emu
config.DATASETS["emu-scorpio-pilot"]["path"]= dataset_emu_scorpio_pilot
config.DATASETS["emu-gp-pilot"]["path"]= dataset_emu_gp_pilot

# - Dynamic dataset registry configuration
config.DATASET_REGISTRY_ENABLED = dataset_registry_enabled
config.DATASET_ALLOWED_ROOTS = dataset_allowed_roots
config.DATASET_ADMIN_IDENTITIES = dataset_admin_identities

#===============================
#==   CREATE APP
#===============================
logger.info("Creating and configuring app ...")
app= create_app(config, jobcfg)
app.app_context().push()

#===============================
#==   INIT OIDC TO APP
#===============================
# - Add Flask OIDC configuration
if use_aai:
	if oidc is None:
		logger.critical("AAI is enabled, but flask_oidc_ex could not be initialized")
		raise RuntimeError("AAI requested but flask_oidc_ex is unavailable")

	logger.info("Initializing OIDC to app ...")
	try:
		oidc.init_app(app)
		logger.info("OIDC initialization completed successfully")

	except Exception as e:
		logger.exception(f"Failed to initialize OIDC to app (err={str(e)})!")
		raise

else:
	logger.info("Starting app without AAI ...")


#===============================
#==   INIT MONGO TO APP
#===============================
if use_db and mongo is not None:
	logger.info("Initializing MongoDB to app ...")

	try:
		mongo.init_app(app)
		logger.info("Flask-PyMongo initialization completed successfully")

		from caesar_rest.pipeline.manager import ensure_indexes

		with app.app_context():
			ensure_indexes()

		logger.info("MongoDB pipeline indexes initialized successfully")

	except Exception as e:
		logger.exception(
			"Failed to initialize MongoDB to app (err=%s)!",
			str(e)
		)
		raise

else:
	logger.info("Starting app without mongo backend ...")

#============================================
#==   INIT KUBERNETES CLIENT (if enabled)
#============================================
if job_scheduler=='kubernetes' and jobmgr_kube is not None:

	# - Setting options
	jobmgr_kube.certfile= config.KUBE_CERTFILE
	jobmgr_kube.cafile= config.KUBE_CERTAUTHFILE
	jobmgr_kube.keyfile= config.KUBE_KEYFILE

	# - Initialize client
	logger.info("Initializing Kube job manager ...")
	try:
		if jobmgr_kube.initialize(configfile=config.KUBE_CONFIG_PATH, incluster=config.KUBE_INCLUSTER)<0:
			logger.error("Failed to initialize Kube job manager, see logs!")
			sys.exit(1)
	except Exception as e:
		logger.error("Failed to initialize Kube job manager (err=%s)!" % str(e))
		sys.exit(1)

#============================================
#==   INIT SLURM CLIENT (if enabled)
#============================================
if job_scheduler=='slurm' and jobmgr_slurm is not None:

	# - Setting options
	jobmgr_slurm.host= config.SLURM_HOST
	jobmgr_slurm.port= config.SLURM_PORT	
	jobmgr_slurm.cluster_queue= config.SLURM_QUEUE
	jobmgr_slurm.keyfile= config.SLURM_KEYFILE
	jobmgr_slurm.username= config.SLURM_USER
	jobmgr_slurm.cluster_batch_workdir= config.SLURM_BATCH_WORKDIR
	jobmgr_slurm.cluster_jobdir= config.SLURM_JOB_DIR
	jobmgr_slurm.cluster_datadir= config.SLURM_DATA_DIR
	jobmgr_slurm.cluster_modeldir= config.SLURM_MODEL_DIR
	jobmgr_slurm.app_jobdir= config.JOB_DIR
	jobmgr_slurm.app_datadir= config.UPLOAD_FOLDER
	jobmgr_slurm.app_modeldir= config.MODEL_DIR
	jobmgr_slurm.max_cores= config.SLURM_MAX_CORE_PER_JOB

	# - Initialize client
	logger.info("Initializing Slurm job manager ...")
	try:
		if jobmgr_slurm.initialize()<0:
			logger.error("Failed to initialize Slurm job manager, see logs!")
			sys.exit(1)
	except Exception as e:
		logger.error("Failed to initialize Slurm job manager (err=%s)!" % str(e))
		sys.exit(1)


###################
##   MAIN EXEC   ##
###################
if __name__ == "__main__":
	
	#===============================
	#==   RUN APP
	#===============================
	if ssl:
		logger.info("Running app on SSL ...")
		app.run(debug=debug, ssl_context='adhoc')
	else:
		logger.info("Running app ...")
		app.run(debug=debug)

	sys.exit(0)
