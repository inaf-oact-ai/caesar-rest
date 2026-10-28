#! /usr/bin/env python

##############################
#   MODULE IMPORTS
##############################
# Import standard modules
import os
import sys
import uuid

# Import module files
##from caesar_rest.data_manager import DataManager ## DEPRECATED
from caesar_rest.job_configurator import JobConfigurator

import structlog

##############################
#   APP CONFIG CLASS
##############################

class Config(object):
	""" Class holding configuration options for Flask app """

	# - Flask Options
	DEBUG = False
	TESTING = False
	SECRET_KEY= uuid.uuid4().hex
	UPLOAD_FOLDER= '/opt/caesar-rest/data'
	MAX_CONTENT_LENGTH= 1000 * 1024 * 1024 # 16 MB

	# - Additional options
	JOB_DIR= '/opt/caesar-rest/jobs'
	MODEL_DIR= '/opt/caesar-rest/models'
	UPLOAD_ALLOWED_FILE_FORMATS= set(['png', 'jpg', 'jpeg', 'gif', 'fits', 'json'])
	JOB_MONITORING_PERIOD= 5 # in seconds

	JOB_SCHEDULER= 'slurm' # Options are: {'celery', 'kubernetes', 'slurm'}

	# - VOLUME MOUNTS options
	MOUNT_RCLONE_VOLUME= False
	MOUNT_VOLUME_PATH= '/mnt/storage'
	RCLONE_REMOTE_STORAGE= 'neanias-nextcloud'
	RCLONE_REMOTE_STORAGE_PATH= '.'
	RCLONE_SECRET_NAME= 'rclone-secret'

	# - KUBERNETES options
	KUBE_CONFIG_PATH= '' # searches by default in $HOME/.kube/config or in $KUBECONFIG
	KUBE_INCLUSTER= True # if True assume client is running inside a pod deployed in same cluster, if False client is external to cluster
	KUBE_CERTFILE= ''
	KUBE_KEYFILE= ''
	KUBE_CERTAUTHFILE= ''

	# - SLURM options
	SLURM_KEYFILE= ''
	SLURM_QUEUE= 'normal'
	SLURM_USER= 'cirasa'
	SLURM_HOST= 'lofar-gpu-01.oact.inaf.it'	# 'cirasa host'
	SLURM_PORT= 6820
	SLURM_BATCH_WORKDIR= '/opt/caesar-rest/batchlogs'
	SLURM_JOB_DIR= '/mnt/storage/jobs'  # Path at which the job directory is mounted in Slurm cluster 
	SLURM_DATA_DIR= '/mnt/storage/data' # Path at which the data directory is mounted in Slurm cluster
	SLURM_MODEL_DIR= '/mnt/storage/models' # Path at which the models directory is mounted in Slurm cluster
	SLURM_CAESAR_JOB_IMAGE= '/opt/containers/caesar/caesar-job_latest.sif'
	SLURM_MASKRCNN_JOB_IMAGE= '/opt/containers/mrcnn/mrcnn-detect_latest.sif'
	SLURM_AEGEAN_JOB_IMAGE= '/opt/containers/aegean/aegean-job_latest.sif'
	SLURM_CUTEX_JOB_IMAGE= '/opt/containers/cutex/cutex-job_latest.sif'
	SLURM_CNN_CLASSIFIER_JOB_IMAGE= '/opt/containers/sclassifier/cnn-classifier_latest.sif'
	SLURM_VIT_CLASSIFIER_JOB_IMAGE= '/opt/containers/sclassifier-vit/vit-classifier_latest.sif'
	SLURM_UMAP_JOB_IMAGE= '/opt/containers/sclassifier/umap_latest.sif'
	SLURM_OUTLIER_FINDER_JOB_IMAGE= '/opt/containers/sclassifier/outlier_finder_latest.sif'
	SLURM_HDBSCAN_JOB_IMAGE= '/opt/containers/sclassifier/hdbscan_latest.sif'
	SLURM_SIMSEARCH_JOB_IMAGE= '/opt/containers/sclassifier/similarity-search_latest.sif'
	SLURM_CAESAR_YOLO_JOB_IMAGE= '/opt/containers/caesar-yolo/caesar-yolo-job_latest.sif'
	SLURM_SFFORECASTER_JOB_IMAGE= '/opt/containers/sfforecaster/sfforecaster-job_latest.sif'
	SLURM_FEXTRACTOR_TF_JOB_IMAGE= '/opt/containers/fextractor/fextractor-tf_latest.sif'
	SLURM_FEXTRACTOR_TORCH_JOB_IMAGE= '/opt/containers/fextractor/fextractor-torch_latest.sif'
	SLURM_FEXTRACTOR_CHRONOS_JOB_IMAGE= '/opt/containers/fextractor/fextractor-chronos_latest.sif'
	SLURM_FEXTRACTOR_MOIRAI_JOB_IMAGE= '/opt/containers/fextractor/fextractor-moirai_latest.sif'
	SLURM_FEXTRACTOR_FATS_JOB_IMAGE= '/opt/containers/fextractor/fextractor-fats_latest.sif'
	SLURM_FEXTRACTOR_LICU_JOB_IMAGE= '/opt/containers/fextractor/fextractor-licu_latest.sif'
	SLURM_FEXTRACTOR_FALCON_JOB_IMAGE= '/opt/containers/fextractor/fextractor-falcon_latest.sif'
	SLURM_OXKAT_JOB_IMAGE= '/opt/containers/oxkat/oxkat-caesar.sif'

	SLURM_MAX_CORE_PER_JOB= 4 # Maximum number of cores reserved for a job
	
	# - AAI options
	USE_AAI = False
	OIDC_CLIENT_SECRETS = 'config/client_secrets.json'
	OIDC_OPENID_REALM = 'neanias-development'
	OIDC_SCOPES = ['openid', 'email', 'profile']

	# - MONG DB options
	USE_MONGO = False
	MONGO_HOST= 'localhost'
	MONGO_PORT= 27017
	MONGO_DBNAME= 'caesardb' 
	MONGO_URI= 'mongodb://localhost:27017/caesardb'

	# - CAESAR app options
	CAESAR_JOB_IMAGE= 'sriggi/caesar-job:latest'
	
	# - Mask R-CNN app options
	MASKRCNN_JOB_IMAGE= 'sriggi/mrcnn-detect:latest'
	MASKRCNN_WEIGHTS= '/opt/Software/MaskR-CNN/install/share/mrcnn_weights.h5'

	# - AEGEAN app options
	AEGEAN_JOB_IMAGE= 'sriggi/aegean-job:latest'

	# - CUTEX app options
	CUTEX_JOB_IMAGE= 'sriggi/cutex-job:latest'
	
	# - IMAGE CNN CLASSIFIER app options
	CNN_CLASSIFIER_JOB_IMAGE= 'sriggi/cnn-classifier:latest'
	
	# - IMAGE ViT CLASSIFIER app options
	VIT_CLASSIFIER_JOB_IMAGE= 'sriggi/vit-classifier:latest'
	
	# - UMAP app options
	UMAP_JOB_IMAGE= 'sriggi/umap:latest'
	
	# - UMAP app options
	OUTLIER_FINDER_JOB_IMAGE= 'sriggi/outlier-finder:latest'
	
	# - HDBSCAN app options
	HDBSCAN_JOB_IMAGE= 'sriggi/hdbscan:latest'
	
	# - SIM SEARCH app options
	SIMSEARCH_JOB_IMAGE= 'sriggi/similarity-search:latest'
	
	# - CAESAR-YOLO app options
	CAESAR_YOLO_JOB_IMAGE= 'sriggi/caesar-yolo-job:latest'
	
	# - SFFORECASTER app options
	SFFORECASTER_JOB_IMAGE= 'sriggi/sfforecaster-job:latest'
	
	# - FEXTRACTOR app options
	FEXTRACTOR_TF_JOB_IMAGE= 'sriggi/fextractor-tf:latest'
	FEXTRACTOR_TORCH_JOB_IMAGE= 'sriggi/fextractor-torch:latest'
	FEXTRACTOR_CHRONOS_JOB_IMAGE= 'sriggi/fextractor-chronos:latest'
	FEXTRACTOR_MOIRAI_JOB_IMAGE= 'sriggi/fextractor-moirai:latest'
	FEXTRACTOR_FATS_JOB_IMAGE= 'sriggi/fextractor-fats:latest'
	FEXTRACTOR_LICU_JOB_IMAGE= 'sriggi/fextractor-licu:latest'
	FEXTRACTOR_FALCON_JOB_IMAGE= 'sriggi/fextractor-falcon:latest'
	
	# - OXKAT app options
	OXKAT_JOB_IMAGE= 'sriggi/oxkat-caesar:latest' ## TO BE CREATED YET!


	# - PIPELINE options	
	# - Generic staged pipeline execution
	# - Disabled by default to preserve existing /job behaviour.
	PIPELINE_STAGED_EXECUTION_ENABLED = False

	# - Applications approved for initial staged-container execution.
	# - Scientific operations remain the responsibility of each container.
	PIPELINE_STAGED_APPLICATIONS = ('oxkat',)

	# - Optional Python interpreter on Slurm compute nodes.
	# - The standalone worker does not require CAESAR-REST to be
	#   installed in this Python environment.
	# - Empty value selects /usr/bin/python3.
	PIPELINE_PYTHON_EXECUTABLE = ''
	
	# - Pipeline artifact retention configs
	PIPELINE_ARTIFACT_RETENTION_ROOT = ''
	PIPELINE_ARTIFACT_RETENTION_MAX_FILE_BYTES = 1024 * 1024 * 1024
	PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES = 1024 * 1024 * 1024 * 1024
	PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES = 100000
	PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH = 16

	# - V2 is disabled for every application by default.
	# - Each enabled application must explicitly define:
	#   1) scientific parameters and accepted values
	#   2) mapping from container CLI options to frozen input names
	PIPELINE_V2_APPLICATIONS = {}

	# - Cluster-visible root corresponding to the application-side
	#   PIPELINE_ARTIFACT_RETENTION_ROOT.
	# - Must be explicitly configured for V2 execution.
	PIPELINE_ARTIFACT_RETENTION_ROOT_CLUSTER = ''


	# - DATASET app options
	# - Dynamic dataset registry options
	#
	# Disabled by default for backward compatibility.
	# Requires MongoDB and authenticated OIDC identities.
	DATASET_REGISTRY_ENABLED = False

	# Only these physical storage roots may contain
	# dynamically registered datasets.
	#
	# All paths must be absolute.
	# Symlinks are resolved during registration.
	DATASET_ALLOWED_ROOTS = []

	# CAESAR-REST dataset administrators.
	#
	# Each identity is represented by:
	#     <OIDC issuer>|<OIDC subject>
	#
	# Example:
	#     https://identity.example.org|admin-subject
	#
	# Do not use email addresses or display names.
	DATASET_ADMIN_IDENTITIES = []
	
	#   NB: paths are to be configured at app deployment phase.
	DATASETS= {
		"smgps": {
			"path": "",
			"description": "A collection of 178,057 image cutouts of size 256x256 pixels extracted from the SARAO MeerKAT Galactic Plane survey (Goedhart+24)."
		},
		"smgps-feats-simclr": {
			"path": "",
			"description": "Feature data (#512 features) obtained with a SimCLR self-supervised pre-trained model from a collection of 178,057 image cutouts of size 256x256 pixels extracted from the SARAO MeerKAT Galactic Plane survey (Goedhart+24)."
		},
		"smgps-feats-siglip": {
			"path": "",
			"description": "Feature data (#512 features) obtained with a SigLIP Vit14 pre-trained model from a collection of 178,057 image cutouts of size 256x256 pixels extracted from the SARAO MeerKAT Galactic Plane survey (Goedhart+24)."
		},
		"smgps-feats-dinov2": {
			"path": "",
			"description": "Feature data (#1024 features) obtained with a DINOv2 vitl14 pre-trained model from a collection of 178,057 image cutouts of size 256x256 pixels extracted from the SARAO MeerKAT Galactic Plane survey (Goedhart+24)."
		},
		"emu-pilot": {
			"path": "",
			"description": "A collection of 55,773 image cutouts of size 256x256 pixels extracted from the ASKAP EMU pilot survey (Norris+2021)."
		},
		"emu": {
			"path": "",
			"description": "A collection of XXX image cutouts of size 256x256 pixels extracted from the ASKAP EMU main survey (Hopkins+2024)."
		},
		"emu-scorpio-pilot": {
			"path": "",
			"description": "A collection of 12,757 image cutouts of size 256x256 pixels extracted from the ASKAP EMU SCORPIO pilot survey (phase 1) (Umana+2021)."
		},
		"emu-gp-pilot": {
			"path": "",
			"description": "A collection of 38,998 image cutouts of size 256x256 pixels extracted from the ASKAP EMU Galactic Plane pilot observations (phase 2)."
		},
	} # close datasets
	
	# - Logging configuration
	LOG_TO_FILE= False
	LOG_DIR= '/opt/caesar-rest/logs'
	LOG_FILE= 'app_logs.json'
	LOG_LEVEL= 'INFO'

#	LOGGING = {
#		"version": 1,
#		"disable_existing_loggers": False,
#		"formatters": {
#			"json_formatter": {
#				"()": structlog.stdlib.ProcessorFormatter,
#				"processor": structlog.processors.JSONRenderer(),
#			},
#			"plain_console": {
#				"()": structlog.stdlib.ProcessorFormatter,
#				"processor": structlog.dev.ConsoleRenderer(),
#			},
#			"key_value": {
#				"()": structlog.stdlib.ProcessorFormatter,
#				"processor": structlog.processors.KeyValueRenderer(key_order=['timestamp', 'level', 'event', 'logger']),
#			},
#		},
#		"handlers": {
#			"console": {
#				"class": "logging.StreamHandler",
#				"formatter": "plain_console",
#			},
#			"json_file": {
#				"class": "logging.handlers.RotatingFileHandler",
#				"filename": os.path.join(LOG_DIR, LOG_FILE),
#				"formatter": "json_formatter",
#				"maxBytes": 5*1024*1024, # 5 MB
#				"backupCount": 2
#			},
#		},
#		"loggers": {
#			'app_caesar': {
#				'handlers': ['console', 'json_file'],
#				'level': LOG_LEVEL,
#			}
#		}
#	}


#	structlog.configure(
#		processors=[
#			structlog.stdlib.filter_by_level,
#			structlog.processors.TimeStamper(fmt="iso"),
#			structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
#			structlog.stdlib.add_logger_name,
#			structlog.stdlib.add_log_level,
#			structlog.stdlib.PositionalArgumentsFormatter(),
#			structlog.processors.StackInfoRenderer(),
#			structlog.processors.format_exc_info,
#			structlog.processors.UnicodeDecoder(),
#			structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
#		],
#		context_class=structlog.threadlocal.wrap_dict(dict),
#		logger_factory=structlog.stdlib.LoggerFactory(),
#		wrapper_class=structlog.stdlib.BoundLogger,
#		cache_logger_on_first_use=True,
#	)




