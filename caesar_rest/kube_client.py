##############################
#   MODULE IMPORTS
##############################
# Import standard modules
import os
import glob
import signal
import sys
import json
import time
import datetime
from dateutil.tz import tzutc
import logging
import numpy as np
import pprint

# - Import Kubernetes and related modules
import yaml
#from kubernetes import client, config, utils
from kubernetes import client
from kubernetes import config as config_kube

from kubernetes.client.rest import ApiException

# - Import CAESAR-REST modules
from caesar_rest import utils

# - Get logger
#logger = logging.getLogger(__name__)
from caesar_rest import logger

##############################
#      CLASSES
##############################
class KubeJobManager(object):
	""" A wrapper class to manage Kubernetes jobs """    
	
	def __init__(self):

		# - Set default vars
		self.api_instance= None
		self.configfile= ''
		self.incluster= True
		self.config_dict= {}
		self.curr_context= ''
		self.context_dict= {}
		self.cluster_dict= {}
		self.cluster= ''
		self.cluster_host= ''
		self.cluster_user= ''
		self.cluster_namespace= 'default'

		self.certfile= ''
		self.keyfile= ''
		self.cafile= ''
		self.verify_ssl = True
		
		# - Initialize
		#if self.initialize()<0:
		#	errmsg= 'Failed to initialize Kube client from file ' + configfile + '!'
		#	logger.error(errmsg)
		#	raise Exception(errmsg)
		
		
	def parse_config(self):
		""" Parse Kube config yaml file and set some variables """
		
		# - Parse config file to extract some info
		self.config_dict= {}
		try:
			with open(self.configfile, 'r') as f:
				self.config_dict= yaml.safe_load(f)
		except:
			logger.warn("Failed to parse config file %s!" % configfile)
			return -1
	
		if not self.config_dict:
			logger.warn("Kubernetes config is empty dict!")
			return -1
	
		# - Get current context name
		if 'current-context' not in self.config_dict:
			logger.warn("Failed to get current-context in Kube config!")
			return -1
		
		self.curr_context= self.config_dict['current-context']
		if self.curr_context=="" or self.curr_context is None:
			logger.warn("Failed to get current context from Kube config file!")
			return -1

		# - Get current context dict
		self.context_dict= {}
		for item in self.config_dict['contexts']:
			context= item['name']
			if context==self.curr_context:
				self.context_dict= item['context']	
				break

		if not self.context_dict:
			logger.warn("Empty context dictionary parsed from Kube config!")
			return -1

		# - Set variables needed to instantiate the Kube config class
		if 'namespace' in self.context_dict:
			self.cluster_namespace= self.context_dict['namespace']
		else:
			logger.warn("No namespace key in context dictionary!")
			return -1

		if 'cluster' in self.context_dict:
			self.cluster= self.context_dict['cluster']
		else:
			logger.warn("No cluster key in context dictionary!")
			return -1
	
		if 'user' in self.context_dict:
			self.cluster_user= self.context_dict['user']
		else:
			logger.warn("No user key in context dictionary!")
			return -1

		# - Set cluster info (e.g. ipaddress, etc)
		self.cluster_dict= {}
		for item in self.config_dict['clusters']:
			cluster= item['name']
			if context==self.curr_context:
				self.context_dict= item['context']	
				break

		if not self.context_dict:
			logger.warn("Empty context dictionary parsed from Kube config!")
			return -1
			

		return 0

	def set_config(self):
		""" Set configuration info from configfile """

		# - Create default "empty" configuration
		self.configuration = client.Configuration()

		# - Load Kube configuration from file
		if self.incluster:
			logger.info("Loading Kube configuration incluster mode...")
			try:
				config_kube.load_incluster_config(client_configuration=self.configuration)
			except Exception as e:
				logger.warn("Failed to load kube config incluster mode (err=%s)!" % str(e))
				return -1
		else:			
			try:
				if self.configfile=="":
					logger.info("Loading Kube configuration from default config file ...")
					config_kube.load_kube_config(client_configuration=self.configuration)
				else:
					logger.info("Loading Kube configuration from config file %s ..." % self.configfile)
					config_kube.load_kube_config(config_file=self.configfile,client_configuration=self.configuration)
			except Exception as e:
				logger.warn("Failed to load kube config (err=%s)!" % str(e))
				return -1

		# - Update authentication fields
		if self.certfile!="":
			logger.info("Setting cert file to %s ..." % self.certfile)
			self.configuration.cert_file= self.certfile
		if self.keyfile!="":
			logger.info("Setting key file to %s ..." % self.keyfile)
			self.configuration.key_file= self.keyfile
		if self.cafile!="":
			logger.info("Setting ssl_ca_cert file to %s ..." % self.cafile)
			self.configuration.ssl_ca_cert = self.cafile
	
		self.configuration.verify_ssl = self.verify_ssl

		# - Get some fields from config
		#   NB: These fields are not available in incluster mode.
		self.cluster_host= self.configuration.host
		self.context_dict= {}

		if self.incluster:
			try:
				self.cluster_namespace= open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()
			except Exception as e:
				logger.warn("Failed to read namespace from kube secret file (err=%s)!" % str(e) )
				return -1
		else:
			try:
				#print("kube config contexts")
				#print(config_kube.list_kube_config_contexts())
				if self.configfile=="":
					self.context_dict= config_kube.list_kube_config_contexts()[1]['context']
				else:
					self.context_dict= config_kube.list_kube_config_contexts(config_file=self.configfile)[1]['context']
			except Exception as e:
				logger.warn("Failed to get context dictionary from config (err=%s)!" % str(e) )
				return -1

			if self.context_dict is None:
				logger.warn("context dictionary read from config is None!")
				return -1
		
			if 'namespace' in self.context_dict:
				self.cluster_namespace= self.context_dict['namespace']
			else:
				logger.warn("No namespace key in context dictionary!")
				return -1

			if 'cluster' in self.context_dict:
				self.cluster= self.context_dict['cluster']
			else:
				logger.warn("No cluster key in context dictionary!")
				return -1

			if 'user' in self.context_dict:
				self.cluster_user= self.context_dict['user']
			else:
				logger.warn("No user key in context dictionary!")
				return -1
		


		print("== KUBE CLIENT CONFIG ==")
		print("cluster=%s (host=%s)" % (self.cluster, self.cluster_host))
		print("user=%s" % self.cluster_user)
		print("namespace=%s" % self.cluster_namespace)
		print("certfile=%s" % self.configuration.cert_file)
		print("keyfile=%s" % self.configuration.key_file)
		print("ssl_ca_certfile=%s" % self.configuration.ssl_ca_cert)
		print("========================")

		return 0


	def create_batch_api_instance(self):
		""" Create batch API client """

		try:
			self.api_instance= client.BatchV1Api(client.ApiClient(self.configuration))
		except:
			logger.error("Failed to create batch API instance, returning null!")
			return -1

		return 0


	def initialize(self, configfile='', incluster=True):
		""" Initialize configuration """

		# - Set config options
		self.configfile= configfile
		self.incluster= incluster

		# - Set configuration info
		if self.set_config()<0:
			logger.warn("Failed to set client configuration!")
			return -1

		# - Create batch API instance
		if self.create_batch_api_instance()<0:
			logger.warn("Failed to create batch API instance!")
			return -1		

		return 0
		

	#============================
	#==     GET JOB STATUS
	#============================
	def get_job_status(self, job_name):
		""" Retrieve job status """

		res= {}
		res['job_id']= job_name
		res['pid']= job_name
		res['state']= ''
		res['status']= ''
		res['exit_code']= ''
		res['elapsed_time']= ''

		# - Get job with given name
		submitted_job= None
		try:
			submitted_job = self.api_instance.read_namespaced_job(
				name=job_name, 
				namespace=self.cluster_namespace, 
				pretty=True
			)
			#pprint(submitted_job)

		except ApiException as e:
			logger.warn("Exception when calling BatchV1Api->read_namespaced_job_status: %s" % str(e), action="jobstatus") 
			raise e

		# - Compute job status
		jobstatus_obj = submitted_job.status
		jobcond= jobstatus_obj.conditions
		nactive= jobstatus_obj.active
		nfailed= jobstatus_obj.failed
		nsucceeded= jobstatus_obj.succeeded
		jobcond= jobstatus_obj.conditions

		#print("jobstatus_obj")
		#print(jobstatus_obj)

		# - Map state
		pending= (nactive==0 and nfailed==0 and nsucceeded==0) or (nactive==None and nfailed==None and nsucceeded==None)
		failed= ( (nfailed is not None and nfailed>=1) and (nsucceeded==0 or nsucceeded==None))
		success= ( (nsucceeded is not None and nsucceeded>=1) and (nfailed==0 or nfailed==None))
		running= ( (nactive is not None and nactive>=1) and (nsucceeded==0 or nsucceeded==None) and (nfailed==0 or nfailed==None) )
		if pending:
			res['state']= 'PENDING'
			res['status']= 'Job present in cluster but pod not yet running'
		if running:
			res['state']= 'RUNNING'
			res['status']= 'Job pod is running'
		if failed:
			res['state']= 'FAILURE'
			errmsg= ''
			if jobcond is not None and len(jobcond)>0:
				errmsg= jobcond[0].message
			res['status']= 'Job failed (err=' + errmsg + ')'
		if success:
			res['state']= 'SUCCESS'
			res['status']= 'Job completed with success'
		
		# - Compute elapsed time
		if success:
			t0= jobstatus_obj.start_time
			t1= jobstatus_obj.completion_time
			elapsed= (t1-t0).total_seconds()
			res['elapsed_time']= elapsed

		# - Get exit code (possibly not supported!)
		# ...
		# ...
	
		
		return res

	def print_jobs(self):
		""" Print jobs inside namespace """
	
		try:
			jobs = self.api_instance.list_namespaced_job(
				namespace=self.cluster_namespace, 
				pretty=True	
			)
			pprint(jobs)

		except ApiException as e:
			logger.warn("Exception when calling BatchV1Api->list_namespaced_job: %s" % e)
			return

	#============================
	#==     DELETE JOB
	#============================
	def delete_job(self, job_name):
		""" Delete job and relative pod (TBD) """
		
		logger.info("Cleaning up job %s ..." % job_name, action="canceljob")
		try: 
			# - Setting Grace Period to 0 means delete ASAP.
			#   Propagation policy makes the Garbage cleaning Async
			res= self.api_instance.delete_namespaced_job(
				name=job_name,
				namespace=self.cluster_namespace,
				pretty=True,
				grace_period_seconds= 0, 
				propagation_policy='Background'
			)
			print(res)
            
		except ApiException as e:
			logger.warn("Exception when calling BatchV1Api->delete_namespaced_job: %s" % str(e), action="canceljob")
			return -1

		return 0


	#============================
	#==     CREATE JOB
	#============================
	def create_job(self, image, job_name="", env_vars={}, vol_mounts=[], volumes=[], security_context=None, pod_security_context=None, label="job", image_pull_policy="Always", ttl=60):
		""" Create a V1 Job object """

		# - Generate job name if not given
		if job_name=="":
			job_name= utils.get_uuid()

		# - Generate env vars from given dictionary
		env_list = []
		for env_name, env_value in env_vars.items():
			env_list.append( client.V1EnvVar(name=env_name, value=env_value) )
		
		# - Create the container
		container= None
		try:
			container = client.V1Container(
  			name=job_name,
				image=image,
				env=env_list,
				image_pull_policy=image_pull_policy,
				security_context=security_context,
				volume_mounts=vol_mounts
			)
		except:
			logger.warn("Failed to create job container object!", action="submitjob")
			return None

		# - Create and configurate pod spec section
		template= None
		try:
			template = client.V1PodTemplateSpec(
				metadata=client.V1ObjectMeta(labels={"app": label}),
				spec=client.V1PodSpec(
					restart_policy="Never", 
					containers=[container], 
					security_context=pod_security_context, 
					volumes=volumes
				)
			)
		except:
			logger.warn("Failed to create the job template object!", action="submitjob")
			return None

		# - Create the specification of deployment
		spec= None
		try:
			spec = client.V1JobSpec(
				template=template,
				backoff_limit=0,
				ttl_seconds_after_finished=ttl
			)
		except:
			logger("Failed to create the job spec object!", action="submitjob")
			return None

		# - Instantiate the job object
		job= None
		try:
			job = client.V1Job(
				api_version="batch/v1",
				kind="Job",
				metadata=client.V1ObjectMeta(name=job_name),
				spec=spec
			)
		except:
			logger.warn("Failed to create job object!", action="submitjob")
			return None
			
		return job


	#===============================================
	#==     CREATE JOB WITH RCLONE MOUNTED VOLUME
	#===============================================
	def create_job_rclone(
		self, 
		image, 
		job_args, 
		label, 
		job_name="", 
		job_outdir="", 
		rclone_storage_name="neanias-nextcloud", 
		rclone_secret_name="rclone-secret", 
		rclone_storage_path=".", 
		rclone_mount_path="/mnt/storage",
		app_mode="",
	):
		""" Create a standard job object with rclone mounted volume """

		# - Check job options
		if job_args=="":
			logger.warn("Empty job args!", action="submitjob")
			return None

		#############################
		###     CREATE JOB SPECS
		#############################
		# - Check env vars
		env_vars= {
			"JOB_OPTIONS": job_args,
			"JOB_OUTDIR": job_outdir,
			"MOUNT_RCLONE_VOLUME": "1",
			"RCLONE_REMOTE_STORAGE": rclone_storage_name,
			"RCLONE_REMOTE_STORAGE_PATH": rclone_storage_path,
			"MOUNT_VOLUME_PATH": rclone_mount_path,
			"RCLONE_MOUNT_WAIT_TIME": "10"
		}
		
		if app_mode:
			env_vars["APP_MODE"]= app_mode

		# - Set security context	
		capabilities= client.V1Capabilities(add=["SYS_ADMIN"])
		security_context= client.V1SecurityContext(
			privileged=True,
			capabilities=capabilities
		)

		# - Set volumes
		rclone_vol= client.V1Volume(name="rclone-secret", secret=client.V1SecretVolumeSource(secret_name=rclone_secret_name))
		fuse_vol= client.V1Volume(name="fuse", host_path=client.V1HostPathVolumeSource(path="/dev/fuse"))
		volumes= [rclone_vol, fuse_vol]

		# - Set volume mounts
		rclone_vol_mount= client.V1VolumeMount(name="rclone-secret",mount_path="/root/.config/rclone/")
		fuse_vol_mount= client.V1VolumeMount(name="fuse",mount_path="/dev/fuse")
		vol_mounts= [rclone_vol_mount,fuse_vol_mount]
		
		# - Create pod security context
		pod_security_context= client.V1PodSecurityContext(fs_group=1000)

		#############################
		###     CREATE JOB
		#############################
		# - Create job
		job= self.create_job(
			image, 
			job_name=job_name, 
			env_vars=env_vars, 
			vol_mounts=vol_mounts, 
			volumes=volumes, 
			security_context=security_context, 
			pod_security_context=pod_security_context, 
			label=label, 
			image_pull_policy="Always",
			ttl=60
		)

		return job


	#============================
	#==     SUBMIT JOB
	#============================
	def submit_job(self, job):
		""" Submit job object to current namespace """

		jobout= None
		try:
			jobout= self.api_instance.create_namespaced_job(
				namespace=self.cluster_namespace, 
				body=job, 
				pretty=True
			)
			
		except ApiException as e:
			logger.warn("Exception when calling BatchV1Api->create_namespaced_job: %s" % str(e), action="submitjob")
			return None
	
		return jobout



