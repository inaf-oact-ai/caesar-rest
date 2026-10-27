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

# Import mongo
from pymongo import MongoClient

# - caesar_rest modules
import caesar_rest
from caesar_rest import __version__, __date__
from caesar_rest import logger
from caesar_rest import jobmgr_kube
from caesar_rest import jobmgr_slurm
from caesar_rest import job_monitor
from caesar_rest.job_monitor import monitor_jobs
from caesar_rest.pipeline import status as pipeline_status_sync

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
	parser.add_argument('-job_scheduler','--job_scheduler', dest='job_scheduler', default='kubernetes', required=False, type=str, help='Job scheduler to be used. Options are: {kubernetes,slurm} (default=kubernetes)')
	parser.add_argument('-job_monitoring_period','--job_monitoring_period', dest='job_monitoring_period', default=30, required=False, type=int, help='Job monitoring poll period in seconds') 
	parser.add_argument('-dbhost','--dbhost', dest='dbhost', default='localhost', required=False, type=str, help='Host of MongoDB database (default=localhost)')
	parser.add_argument('-dbname','--dbname', dest='dbname', default='caesardb', required=False, type=str, help='Name of MongoDB database (default=caesardb)')
	parser.add_argument('-dbport','--dbport', dest='dbport', default=27017, required=False, type=int, help='Port of MongoDB database (default=27017)')

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
	parser.add_argument('-slurm_host','--slurm_host', dest='slurm_host', default='SLURM_HOST', required=False, type=str, help='Slurm cluster host/ipaddress')
	parser.add_argument('-slurm_port','--slurm_port', dest='slurm_port', default=6820, required=False, type=int, help='Slurm rest service port')
	
	# - Log options
	parser.add_argument('-loglevel','--loglevel', dest='loglevel', default='INFO', required=False, type=str, help='Log level to be used (default=INFO)')
	parser.add_argument('--logtofile', dest='logtofile', action='store_true')	
	parser.set_defaults(logtofile=False)
	parser.add_argument('-logdir','--logdir', dest='logdir', default='/opt/caesar-rest/logs', required=False, type=str, help='Directory where to store logs')
	parser.add_argument('-logfile','--logfile', dest='logfile', default='app_logs.json', required=False, type=str, help='Name of json log file')
	parser.add_argument('-logfile_maxsize','--logfile_maxsize', dest='logfile_maxsize', default=5.0, required=False, type=float, help='Max file size in MB (default=5)')

	# - Automatic retention of completed pipeline outputs.
	parser.add_argument(
		'--pipeline_artifact_retention_root',
		default='',
		type=str,
		help='Storage root for automatically retained pipeline artifacts'
	)

	parser.add_argument(
		'--pipeline_artifact_retention_max_file_bytes',
		default=1024 * 1024 * 1024,
		type=int
	)

	parser.add_argument(
		'--pipeline_artifact_retention_max_directory_bytes',
		default=1024 * 1024 * 1024 * 1024,
		type=int
	)

	parser.add_argument(
		'--pipeline_artifact_retention_max_directory_entries',
		default=100000,
		type=int
	)

	parser.add_argument(
		'--pipeline_artifact_retention_max_directory_depth',
		default=16,
		type=int
	)

	args = parser.parse_args()	

	return args


###########################
##     MAIN
###########################
def main():
	""" Main function """

	#===========================
	#==   PARSE ARGS
	#===========================
	logger.info("Parsing cmd line arguments ...")
	try:
		args= get_args()
	except Exception as ex:
		logger.error("Failed to get and parse options (err=%s)",str(ex))
		sys.exit(1)

	# - Main options
	job_monitoring_period= args.job_monitoring_period
	job_scheduler= args.job_scheduler
	if job_scheduler!='kubernetes' and job_scheduler!='slurm':
		logger.error("Unsupported job scheduler (hint: supported are {kubernetes,slurm})!")
		sys.exit(1)

	if job_scheduler=='kubernetes' and jobmgr_kube is None:
		logger.error("Chosen scheduler is Kubernetes but kube client failed to be instantiated (see previous logs)!")
		sys.exit(1)
		
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

	#===============================
	#==   INIT MONGO CLIENT
	#===============================
	logger.info("Initializing MongoDB client, connecting to DB (dbhost=%s, dbname=%s, dbport=%s) ..." % (args.dbhost,args.dbname,args.dbport))
	client= None
	dbport_int= int(args.dbport)
	try:
		client= MongoClient(args.dbhost, dbport_int)
	except Exception as e:
		errmsg= 'Exception caught when connecting to DB server (err=' + str(e) + ')!' 
		logger.error(errmsg)
		sys.exit(1)
		
	if client and client is not None:
		logger.info("Connected to db %s..." % args.dbname)
	else:
		logger.error("Cannot connect to DB server!")
		sys.exit(1)

	db= None
	try:
		db= client[args.dbname]
	except Exception as e:
		errmsg= 'Exception caught when connecting to DB ' + args.dbname + ' (err=' + str(e) + ')!' 
		logger.error(errmsg)
		sys.exit(1)

	if db is None:
		logger.error("DB instance is None!")
		sys.exit(1)

	#============================================
	#==   INIT KUBERNETES CLIENT (if enabled)
	#============================================
	if job_scheduler=='kubernetes' and jobmgr_kube is not None:

		# - Setting options
		jobmgr_kube.certfile= args.kube_certfile
		jobmgr_kube.cafile= args.kube_cafile
		jobmgr_kube.keyfile= args.kube_keyfile

		# - Initialize client
		logger.info("Initializing Kube job manager ...")
		try:
			if jobmgr_kube.initialize(configfile=args.kube_config, incluster=args.kube_incluster)<0:
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
		jobmgr_slurm.host= args.slurm_host
		jobmgr_slurm.port= args.slurm_port
		jobmgr_slurm.keyfile= args.slurm_keyfile
		jobmgr_slurm.username= args.slurm_user
		
		# - Initialize client
		logger.info("Initializing Slurm job manager ...")
		try:
			if jobmgr_slurm.initialize()<0:
				logger.error("Failed to initialize Slurm job manager, see logs!")
				sys.exit(1)
		except Exception as e:
			logger.error("Failed to initialize Slurm job manager (err=%s)!" % str(e))
			sys.exit(1)

	#============================================
	#==   PIPELINE ARTIFACT RETENTION
	#============================================
	retention_root = args.pipeline_artifact_retention_root.strip()

	if retention_root:
		if (
			not os.path.isabs(retention_root)
			or os.path.normpath(retention_root) != retention_root
			or retention_root == '/'
		):
			logger.error('Invalid pipeline artifact retention root')
			sys.exit(1)

		retention_config = {
			'PIPELINE_ARTIFACT_RETENTION_ROOT': retention_root,
			'PIPELINE_ARTIFACT_RETENTION_MAX_FILE_BYTES':
				args.pipeline_artifact_retention_max_file_bytes,
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_BYTES':
				args.pipeline_artifact_retention_max_directory_bytes,
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_ENTRIES':
				args.pipeline_artifact_retention_max_directory_entries,
			'PIPELINE_ARTIFACT_RETENTION_MAX_DIRECTORY_DEPTH':
				args.pipeline_artifact_retention_max_directory_depth
		}

		if any(
			not isinstance(value, int) or value <= 0
			for key, value in retention_config.items()
			if key != 'PIPELINE_ARTIFACT_RETENTION_ROOT'
		):
			logger.error('Invalid pipeline artifact retention limits')
			sys.exit(1)

		pipeline_status_sync.configure_monitor_retention(retention_config)

		logger.info(
			'Automatic pipeline artifact retention enabled (root=%s)' %
			retention_root
		)
	else:
		pipeline_status_sync.configure_monitor_retention({})
		logger.info('Automatic pipeline artifact retention not configured')

	#============================================
	#==   MONITORING LOOP
	#============================================
	try:
		while True:
			# - Monitor jobs in DB
			logger.info("Monitoring jobs ...")
			if monitor_jobs(db)<0:
				logger.warn("Failed to monitor jobs (see logs) ...")

			# - Sleeping a bit before monitoring again
			logger.info("Sleeping %s seconds ..." % job_monitoring_period)
			time.sleep(job_monitoring_period)
						
	except KeyboardInterrupt:
		logger.info("Job monitoring interrupted with ctrl-c signal")
		return -1	


	return 0

###################
##   MAIN EXEC   ##
###################
if __name__ == "__main__":	
	#sys.exit(main())
	main()

