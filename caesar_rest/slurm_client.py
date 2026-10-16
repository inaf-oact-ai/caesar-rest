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
from datetime import datetime, timedelta, timezone
from dateutil.tz import tzutc
import logging
import numpy as np
import pprint
import errno

# - Import additional modules
import requests
import jwt
from jwt import JWT
from jwt.jwa import HS256
from jwt.jwk import jwk_from_dict
from jwt.utils import b64decode,b64encode,get_time_from_int

# - Import CAESAR-REST modules
from caesar_rest import utils

# - Get logger
from caesar_rest import logger
#logger = logging.getLogger(__name__)

##############################
#      CLASSES
##############################
class SlurmJobManager(object):
	""" A wrapper class to manage Slurm jobs """    
	
	def __init__(self):
	
		# - Options to be set
		self.host= ''
		self.port= 6820
		self.username= ''
		self.keyfile= '' # Path of Slurm REST key file, e.g. /etc/slurm/jwt.key
		
		# - Options to be set for job submission
		self.cluster_queue= ''
		self.cluster_batch_workdir= ''
		self.cluster_jobdir= ''
		self.cluster_datadir= ''
		self.cluster_modeldir= ''
		self.app_jobdir= ''
		self.app_datadir= ''
		self.app_modeldir= ''
		self.sleep_before_run= True # to enable job directory to be created in nextcloud
		self.sleeptime_before_run= 10
		self.max_cores= 4
			
		# - Options read or automatically computed from others
		self.cluster_url= ''
		self.key= ''
		self.token= '' # JWT token
		self.request_timeout= 10


	#############################
	##  CHECK/SET VARS
	#############################
	def set_cluster_url(self):
		""" Set cluster url """
		
		self.cluster_url= 'http://' + self.host + ':' + str(self.port) + '/slurm/v0.0.36' 


	def check_submit_vars(self):
		""" Check mandatory vars to be set before submitting a job """

		if self.cluster_queue=="":
			logger.warn("Empty cluster queue given, check given app options!")
			return -1

		if self.cluster_batch_workdir=="":
			logger.warn("Slurm cluster batch workdir not given...setting it to /home/%s ..." % self.username)
			self.cluster_batch_workdir= '/home/' + self.username

		if self.app_jobdir=="":
			logger.warn("Empty app jobdir given, check given app options!")
			return -1

		if self.app_datadir=="":
			logger.warn("Empty app datadir given, check given app options!")
			return -1
			
		if self.app_modeldir=="":
			logger.warn("Empty app modeldir given, check given app options!")
			return -1

		if self.cluster_jobdir=="":
			logger.warn("Empty cluster jobdir given, check given app options!")
			return -1

		if self.cluster_datadir=="":
			logger.warn("Empty cluster datadir given, check given app options!")
			return -1
			
		if self.cluster_modeldir=="":
			logger.warn("Empty cluster modeldir given, check given app options!")
			return -1
		
		return 0

	#############################
	##   INITIALIZE
	#############################
	def initialize(self):
		""" Initialize client """

		# - Check if required field were set
		if self.username=="":
			logger.warn("Empty cluster username given, check given app options!")
			return -1

		if self.host=="":
			logger.warn("Empty cluster hostname given, check given app options!")
			return -1

		if self.keyfile=="":
			logger.warn("Empty Slurm key file given, check given app options!")
			return -1

		if not os.path.isfile(self.keyfile):
			logger.warn("Slurm key file %s not existing on filesystem!" % self.keyfile)
			return -1

		
		# - Set cluster url
		self.set_cluster_url()

		# - Read private key
		if self.read_key()<0:
			logger.warn("Failed to read Slurm rest private key!")
			return -1

		# - Generate a token
		if self.generate_token()<0:
			logger.warn("Failed to generate Slurm JWT token!")
			return -1

		# ...
		# ...

		return 0

	

	#############################
	##   READ KEY
	#############################
	def read_key(self):
		""" Read private key """
		
		# - Read private key
		try:
			with open(self.keyfile, "rb") as f:
				priv_key= f.read()
				self.key = jwk_from_dict({'kty': 'oct', 'k': b64encode(priv_key)})

		except Exception as e:
			logger.warn("Failed to read private key from file %s (err=%s)!" % (self.keyfile,str(e)))
			return -1

		return 0

	

	####################################
	##   GENERATE/VALIDAT AUTH TOKEN
	####################################
	def generate_token(self, duration=3600):
		""" Generate a token for user from key with duration in seconds """

		# - Taken from https://slurm.schedmd.com/jwt.html#:~:text=Version%2020.11-,JSON%20Web%20Tokens%20(JWT)%20Authentication,connecting%20to%20slurmctld%20and%20slurmdbd.
		now= time.time()
		expiration_time= int(now + int(duration))
		message = {
			"exp": expiration_time,
			"iat": int(now),
			"sun": self.username
		}

		# - Generate token
		jwt_token= ''
		try:
			jwt_instance = JWT()
			jwt_token= jwt_instance.encode(message, self.key, alg='HS256')
		except Exception as e:
			logger.warn("Failed to generate token (err=%s)" % str(e))
			return -1

		if jwt_token=="" or jwt_token is None:
			logger.warn("Generate token is empty string or None, something went wrong, do not update token!")
			return -1
		else:
			self.token= jwt_token

		# - Check token
		if not self.is_token_valid():
			logger.warn("Generated token is invalid, set to empty string.")
			self.token= ""
			return -1

		return 0

	def is_token_active(self):
		""" Check if token is valid and not expired """

		payload= self.decode_token(verify=True, check_exp=True)
		if payload is None:
			return False

		return True
	
	def is_token_valid(self):
		""" Check if token is valid """

		payload= self.decode_token(verify=True)
		if payload is None:
			return False

		return True
		
	def is_token_expired(self):
		""" Check if token is valid and expired """

		payload= self.decode_token(verify=False, check_exp=True)
		if payload is None:
			return True

		return False
		

	def decode_token(self, verify=True, check_exp=False):
		""" Check if token is valid """

		signing_key= None
		if verify:
			signing_key= self.key

		try:
			jwt_instance = JWT()
			payload = jwt_instance.decode(
				self.token, 
				key=signing_key, 
				algorithms=["HS256"],
				do_verify=verify,
				do_time_check=check_exp
			)
			#print(payload)
	
		except jwt.exceptions.JWTDecodeError as e:
			logger.warn("Failed to decode token (err=%s)" % str(e))
			return None

		except Exception as e:
			logger.warn("Exception caught when decoding token (err=%s)" % str(e))
			return None

		return payload

	def get_token_time_left(self):
		""" Returns the number of seconds left before token expiration """

		# - Get token payload
		payload= self.decode_token(verify=True, check_exp=True)
		if payload is None:
			logger.warn("Current token is not valid or expired, cannot get expiration time data!")
			return -999

		# - Get expiration time date
		if 'exp' not in payload:
			logger.warn("Cannot find exp field in token payload!")
			return -999

		try:
			expiration_date= get_time_from_int(payload['exp'])
		except TypeError:
			logger.warn("Invalid expired time field read (expected int)!")
			return -999

		# - Compute time diff wrt now
		now = datetime.now(timezone.utc)
		tdiff= expiration_date-now
		tdiff_sec= tdiff.total_seconds()

		print("tdiff")
		print(tdiff)

		return tdiff_sec
		

	def renew_token(self, time_to_expire_thr=30, duration=3600):
		""" Regenerate token if expiration time is less then given threshold """

		# - Check time left
		tdiff= self.get_token_time_left()
		status= 0
		if tdiff<=0:
			logger.info("Current token is invalid or expired, regenerating ...")
			status= self.generate_token(duration)

		elif tdiff>0 and tdiff<time_to_expire_thr:
			logger.info("Current token is about to expire (tdiff=%f), regenerating ..." % tdiff)
			status= self.generate_token(duration)
		
		else:
			logger.debug("Current token is still valid (expiring in %f seconds) ..." % tdiff)
			status= 0

		return status

	#############################
	##   SUBMIT JOB
	#############################
	def submit_job(self, job_data):
		""" Submit a job to Slurm cluster """

		#####################################
		##  API RESPONSE 
		##  {
  	##     "job_id" : 0,
  	##     "step_id" : "step_id",
  	##     "errors" : [{"errno": 0,"error": "error"}, {"errno" : 0, "error" : "error"}],
  	##     "job_submit_user_msg" : "job_submit_user_msg"
		##  }
		#####################################

		# - Check token is active
		if not self.is_token_active():
			logger.warn("Slurm rest auth token not valid or expired, regenerating it ...", action="submitjob")
			if self.generate_token()<0:
				logger.warn("Failed to regenerate Slurm auth token, cannot submit job!", action="submitjob")
				return None
		 

		# - Set header
		headers = {
			'Content-Type': 'application/json',
			'X-SLURM-USER-NAME': self.username,
			'X-SLURM-USER-TOKEN': self.token,
		}

		# - Set url
		url= self.cluster_url + '/job/submit'

		# - Submit job
		logger.info("Submitting job (data=%s, url=%s) ..." % (job_data, url), action="submitjob")
		jobout= None
		try:
			jobout= requests.post(
				url, 
				headers=headers, 
				data=job_data,
				timeout= self.request_timeout
			)
			print("--> slurm jobout")
			print(jobout)

		except requests.Timeout:
			logger.warn("Failed to submit job to url %s (err=request timeout)" % url, action="submitjob")
			return None

		except requests.ConnectionError:
			logger.warn("Failed to submit job to url %s (err=connection error)" % url, action="submitjob")
			return None

		except Exception as e:
			logger.warn("Failed to submit job to url %s (err=%s)" % (url,str(e)), action="submitjob")
			return None

		# - Parse reply and convert to dictionary
		reply= None
		try:
			reply= json.loads(jobout.text)
		except Exception as e:
			logger.warn("Failed to convert reply to dict (err=%s)!" % str(e), action="submitjob")
			return None

		return reply


	#===============================================
	#==     CREATE JOB WITH PRE-MOUNTED VOLUME
	#===============================================
	def create_job(
		self, 
		image, 
		job_args, 
		inputfile, 
		job_name="", 
		job_outdir="", 
		job_run_opts={},
		app_mode="",
	):
		""" Create a standard job object with rclone mounted volume """

		# - Check mandatory vars to be set
		if self.check_submit_vars()<0:
			logger.warn("Mandatory client option for job submission not set, see logs!", action="submitjob")
			return None

		# - Check job options
		if job_args=="":
			logger.warn("Empty job args given!", action="submitjob")
			return None

		if isinstance(inputfile, list):
			for item in inputfile:
				if item=="":
					logger.warn("Empty inputfile entry given!", action="submitjob")
					return None
		else:
			if inputfile=="":
				logger.warn("Empty inputfile given!", action="submitjob")
				return None	
			

		if job_name=="":
			job_name= utils.get_uuid()

		# - Parse run options
		nthreads= 1
		nproc= 1
		if job_run_opts:
			if 'ncores' in job_run_opts:
				nthreads= job_run_opts["ncores"]
			if 'nproc' in job_run_opts:
				nproc= job_run_opts["nproc"]

		if nthreads>self.max_cores:
			logger.warn("Requested nthreads (%d) exceeds max (%d), set nthreads to max..." % (nthreads,self.max_cores), action="submitjob")
			nthreads= self.max_cores

		if nproc>self.max_cores:
			logger.warn("Requested nproc (%d) exceeds max (%d), set nproc to 1..." % (nproc,self.max_cores), action="submitjob")
			nproc= 1
		

		#################################
		###   SET CLUSTER JOB/DATA DIR
		#################################
		# - Find job & dir directories in Slurm cluster
		#   by replacing app dirs with slurm dirs
		inputfile_cluster= inputfile
		if self.app_datadir!=self.cluster_datadir:
			if isinstance(inputfile, list):
				inputfile_cluster= []

				for item in inputfile:
					if item.find(self.app_datadir)!=0:
						logger.warn("Cannot find app data dir string (%s) in provided inputfile string (%s), this is not expected, return None!" % (self.app_datadir, item), action="submitjob")
						return None

					inputfile_cluster.append(item.replace(self.app_datadir, self.cluster_datadir))

				logger.info("Convert given inputfiles from app refs (%s) to cluster refs (%s) ..." % (inputfile, inputfile_cluster), action="submitjob")

			else:
				if inputfile.find(self.app_datadir)!=0:
					logger.warn("Cannot find app data dir string (%s) in provided inputfile string (%s), this is not expected, return None!" % (self.app_datadir, inputfile), action="submitjob")
					return None

				inputfile_cluster= inputfile.replace(self.app_datadir, self.cluster_datadir)
				logger.info("Convert given inputfile from app ref (%s) to cluster ref (%s) ..." % (inputfile, inputfile_cluster), action="submitjob")


		job_outdir_cluster= job_outdir
		if job_outdir!="" and self.app_jobdir!=self.cluster_jobdir:
			if job_outdir.find(self.app_jobdir)!=0:
				logger.warn("Cannot find app job dir string (%s) in provided job_outdir string (%s), this is not expected, return None!" % (self.app_jobdir, job_outdir), action="submitjob")
				return None
			job_outdir_cluster= job_outdir_cluster.replace(self.app_jobdir, self.cluster_jobdir)
			logger.info("Convert given job_outdir from app ref (%s) to cluster ref (%s) ..." % (job_outdir, job_outdir_cluster), action="submitjob")

		#############################
		###   CREATE JOB SCRIPT
		#############################
		# - Set env vars
		job_dir= ''.join("/home/%s/%s" % (self.username, job_name))

		env_vars= ""
		env_vars+= "".join("--env CHANGE_RUNUSER=0 ")
		env_vars+= "".join("--env JOB_DIR=%s " % job_dir)
		env_vars+= "".join("--env JOB_OPTIONS=\'%s\' " % job_args)
		env_vars+= "".join("--env JOB_OUTDIR=%s " % job_outdir)
		env_vars+= "".join("--env MODEL_DIR=%s " % self.app_modeldir)
		if app_mode:
			env_vars+= "".join("--env APP_MODE=%s " % app_mode)
		
		logger.info("app_modeldir: %s" % (self.app_modeldir))

		# - Set singularity run options
		#   NB: Added --no-home because if container is run as caesar user the home is automatically mounter
		#       and replace container home where the run_job.sh script resides. In this case the job fail because the run_job.sh is not found.
		#       This does not happen if the container is run by other users.
		run_opts= "--containall --no-home "

		# - Set singularity volume mount options
		vol_opts= ""
		vol_opts+= "".join("--scratch %s " % job_dir)
		#vol_opts+= "".join("-B %s " % job_outdir)
		#vol_opts+= "".join("-B %s " % inputfile)	
		if job_outdir_cluster!="":
			vol_opts+= "".join("-B %s:%s " % (job_outdir_cluster, job_outdir))
			logger.info("Binding host %s to container %s ..." % (job_outdir_cluster, job_outdir))
			
		###vol_opts+= "".join("-B %s:%s " % (inputfile_cluster, inputfile)) ## ORIGINAL CODE (BUG?)
		###vol_opts+= "".join("-B %s:%s " % (inputfile, inputfile_cluster)) ## TEST
		vol_opts+= "".join("-B %s:%s " % (self.cluster_datadir, self.app_datadir)) # bind entire data volume (NB: this invalidate previous bind)
		logger.info("Binding host %s to container %s ..." % (self.cluster_datadir, self.app_datadir))
		
		vol_opts+= "".join("-B %s:%s " % (self.cluster_modeldir, self.app_modeldir)) # bind entire data volume (NB: this invalidate previous bind)
		logger.info("Binding host %s to container %s ..." % (self.cluster_modeldir, self.app_modeldir))
		
		if nproc>1:
			vol_opts+= "-B /etc/libibverbs.d "
		
		logger.info("Binding opts: %s" % (vol_opts))
		
		# - Set run command
		cmd= ""
		if nproc>1:
			cmd+= "".join("mpirun --report-bindings --np %d --map-by ppr:%d:node:pe=%d --bind-to core " % (nproc, nproc, nthreads))
		cmd+= "singularity run "
		cmd+= run_opts
		cmd+= vol_opts
		cmd+= env_vars
		cmd+= image
		
		# - Set job script
		script= "#!/bin/bash \n "
		if self.sleep_before_run:
			script+= "".join("sleep %d \n " % self.sleeptime_before_run)
		script+= "".join("%s" % cmd)
		
		logger.info("Slurm script: %s" % script, action="submitjob")

		#############################
		###   CREATE JOB BODY
		#############################
		#  NB: See other options @ https://slurm.schedmd.com/rest_api.html#v0.0.36_job_properties

		# - Set job out log file
		job_logfile= job_outdir + "/job_" + job_name + ".log"

		# - Create job object
		#   NB: This is the minimal options needed. The environment field seems mandatory contrarily to what specified in the doc.
		job_data_obj= {}
		job_data_obj["script"]= script
		job_data_obj["job"]= {
			"name": job_name,
			"environment": {"PATH":"/bin:/usr/bin/:/usr/local/bin/"},
		#	"partition": self.cluster_queue, ## NB: commented for the moment, as suspected to be bugged in slurm
      "current_working_directory": self.cluster_batch_workdir, # this is somewhat needed otherwise slurm tries to write to / and get a permission output error
		#	"current_working_directory": job_outdir,
		# "standard_out": job_logfile,
		# "standard_error": job_logfile,
		#	"tasks_per_node": ncores,
			"cpus_per_task": nthreads,
			"tasks": nproc
		}

		# - Convert dict to string
		job_data= ""
		try:
			job_data= json.dumps(job_data_obj)
		except Exception as e:
			logger.warn("Failed to convert job data to string (err=%s)" % str(e), action="submitjob")
			return None	 

		logger.info("Slurm job data: %s" % job_data, action="submitjob")

		return job_data


	#============================
	#==     GET JOB STATUS
	#============================
	def get_job_statuses(self, job_pids):
		""" Retrieve job status for selected list of jobs """
	
		# - Check pid list
		if not job_pids or job_pids is None:
			logger.warn("Given input list of job pids is empty or None!")
			return None

		# - Check token is active
		if not self.is_token_active():
			logger.warn("Slurm rest auth token not valid or expired, regenerating it ...", action="jobstatus")
			if self.generate_token()<0:
				logger.warn("Failed to regenerate Slurm auth token, cannot submit job!", action="jobstatus")
				return None
		 
		# - Set header
		headers = {
			'Content-Type': 'application/json',
			'X-SLURM-USER-NAME': self.username,
			'X-SLURM-USER-TOKEN': self.token,
		}

		# - Set url
		url= self.cluster_url + '/jobs'

		# - Set request parameters
		job_pids_str= ','.join(map(str, job_pids)) 
		params= {
			"job_name": job_pids_str
		}

		# - Get job statuses
		logger.info("Retrieving job statuses (pids=%s, url=%s) ..." % (job_pids_str, url), action="jobstatus")
		jobout= None
		try:
			jobout= requests.get(
				url, 
				headers=headers,
				params= params,
				timeout= self.request_timeout 
			)
			#print("--> slurm jobout")
			#print(jobout)

		except requests.Timeout:
			logger.warn("Failed to query job status to url %s (err=request timeout)" % url, action="jobstatus")
			return None

		except requests.ConnectionError:
			logger.warn("Failed to query job status to url %s (err=connection error)" % url, action="jobstatus")
			return None

		except Exception as e:
			logger.warn("Failed to query job status to url %s (err=%s)" % (url,str(e)), action="jobstatus")
			return None

		# - Parse reply and convert to dictionary
		reply= None
		try:
			reply= json.loads(jobout.text)
		except Exception as e:
			logger.warn("Failed to convert reply to dict (err=%s)!" % str(e), action="jobstatus")
			return None

		job_objs= reply["jobs"]
		if not job_objs:
			logger.warn("Empty job status list reply, jobs not found or already cleared in Slurm", action="jobstatus")
			return {}

		if len(job_objs)!=len(job_pids):
			logger.warn("Retrieved job status has size different wrt given job pids (possibly some jobs have not been found because already cleared) ...")

		# - Loop over job objs and get data
		resdict= {}
		for job_obj in job_objs:
			res= self.get_job_state_data_from_slurm_obj(job_obj)
			print("res")
			print(res)
			job_pid= str(res['pid'])
			resdict[job_pid]= res

		return resdict
		
		

	def get_job_status(self, job_pid):
		""" Retrieve job status """

		# - Check token is active
		if not self.is_token_active():
			logger.warn("Slurm rest auth token not valid or expired, regenerating it ...", action="jobstatus")
			if self.generate_token()<0:
				logger.warn("Failed to regenerate Slurm auth token, cannot submit job!", action="jobstatus")
				return None
		 
		# - Set header
		headers = {
			'Content-Type': 'application/json',
			'X-SLURM-USER-NAME': self.username,
			'X-SLURM-USER-TOKEN': self.token,
		}

		# - Set url
		url= self.cluster_url + '/job/' + job_pid

		# - Get job status
		logger.info("Retrieving job status (pid=%s, url=%s) ..." % (job_pid, url), action="jobstatus")
		jobout= None
		try:
			jobout= requests.get(
				url, 
				headers=headers,
				timeout= self.request_timeout 
			)
			print("--> slurm jobout")
			print(jobout)

		except requests.Timeout:
			logger.warn("Failed to query job status to url %s (err=request timeout)" % url, action="jobstatus")
			return None

		except requests.ConnectionError:
			logger.warn("Failed to query job status to url %s (err=connection error)" % url, action="jobstatus")
			return None

		except Exception as e:
			logger.warn("Failed to query job status to url %s (err=%s)" % (url,str(e)), action="jobstatus")
			return None

		# - Parse reply and convert to dictionary
		reply= None
		try:
			reply= json.loads(jobout.text)
		except Exception as e:
			logger.warn("Failed to convert reply to dict (err=%s)!" % str(e), action="jobstatus")
			return None

		job_objs= reply["jobs"]
		if not job_objs:
			logger.warn("Empty job status reply, job not found or already cleared in Slurm", action="jobstatus")
			return None
		
		job_obj= job_objs[0]

		# - Set job state response from slurm dict
		res= self.get_job_state_data_from_slurm_obj(job_obj)	

		return res


	def get_job_state_data_from_slurm_obj(self, job_obj):
		""" Set job state data """

		# - Init data
		res= {}
		res['pid']= ''
		res['state']= ''
		res['status']= ''
		res['exit_code']= ''
		res['elapsed_time']= ''

		# - Check obj
		if job_obj is None or not job_obj:
			logger.warn("Given slurm job status dict for job %s is empty or None..." % job_pid)
			return res
		
		# - Get job id
		res['pid']= job_obj["job_id"]

		# - Map state
		#   NB: Slurm returns these states: {"PENDING","COMPLETED","RUNNING","SUSPENDED","CANCELLED","FAILED","TIMEOUT","NODE_FAIL","PREEMPTED","BOOT_FAIL","DEADLINE","OUT_OF_MEMORY"}
		job_state= job_obj["job_state"]
		mapped_state= self.get_job_state_from_slurm_state(job_state)
		res['state']= mapped_state[0]
		res['status']= mapped_state[1]
  
		# - Get elapsed time
		t0= job_obj["start_time"]
		t1= job_obj["end_time"]
		elapsed= (t1-t0)
		res['elapsed_time']= elapsed

		# - Get exit code
		res['exit_code']= job_obj["exit_code"]

		return res


	def get_job_state_from_slurm_state(self, job_state):
		""" Get job state & status mapped from slurm state """
	
		res= ()
		if job_state=="PENDING":
			res= ('PENDING', 'Job queued and waiting for initiation')

		elif job_state=="RUNNING":
			res= ('RUNNING', 'Job executing')

		elif job_state=="COMPLETED":
			res= ('SUCCESS', 'Job completed execution successfully')

		elif job_state=="SUSPENDED":
			res= ('PENDING', 'Job was suspended')

		elif job_state=="CANCELLED":
			res= ('CANCELED', 'Job was canceled by user')
			
		elif job_state=="FAILED":
			res= ('FAILURE', 'Job completed execution unsuccessfully')
	
		elif job_state=="TIMEOUT":
			res= ('TIMED-OUT', 'Job terminated due to time limit reached')
		
		elif job_state=="NODE_FAIL":
			res= ('FAILURE', 'Job terminated due to node failure')
			
		elif job_state=="PREEMPTED":
			res= ('FAILURE', 'Job terminated due to preemption')

		elif job_state=="BOOT_FAIL":
			res= ('FAILURE', 'Job terminated due to node boot failure')
			
		elif job_state=="DEADLINE":
			res= ('FAILURE', 'Job terminated on deadline')

		elif job_state=="OUT_OF_MEMORY":
			res= ('FAILURE', 'Job terminated due to experienced out of memory error')

		else:
			res= ('UNKNOWN', 'Job currently in unknown state (raw state=' + job_state + ')')
			
		return res

	#============================
	#==     DELETE JOB
	#============================
	def delete_job(self, job_pid):
		""" Cancel a job """
		
		# - Check token is active
		if not self.is_token_active():
			logger.warn("Slurm rest auth token not valid or expired, regenerating it ...", action="canceljob")
			if self.generate_token()<0:
				logger.warn("Failed to regenerate Slurm auth token, cannot submit job!", action="canceljob")
				return None
		 
		# - Set header
		headers = {
			'Content-Type': 'application/json',
			'X-SLURM-USER-NAME': self.username,
			'X-SLURM-USER-TOKEN': self.token,
		}

		# - Set url
		url= self.cluster_url + '/job/' + job_pid

		logger.info("Deleting job with pid=%s ..." % job_pid, action="canceljob")
		status_code= 0
		try:
			reply= requests.delete(
				url, 
				headers=headers, 
				timeout= self.request_timeout
			)
			print("--> slurm reply to delete")
			print(reply)

			status_code= reply.status_code	

		except requests.Timeout:
			logger.warn("Failed to delete job with url %s (err=request timeout)" % url, action="canceljob")
			return None

		except requests.ConnectionError:
			logger.warn("Failed to delete job with url %s (err=connection error)" % url, action="canceljob")
			return None

		except Exception as e:
			logger.warn("Failed to delete job with url %s (err=%s)" % (url,str(e)), action="canceljob")
			return None

		# - Check status code
		if status_code==200:
			logger.info("Job with pid=%s deleted with success" % job_pid, action="canceljob")
		else:
			logger.warn("Failed to delete job with pid %s (err=server replied with status code %d)!" % (job_pid,status_code), action="canceljob")
			return -1

		return 0


