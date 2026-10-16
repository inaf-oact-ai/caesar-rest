##############################
#   MODULE IMPORTS
##############################
# Import standard modules
import os
import sys
import json
import time
import datetime
import logging
import numpy as np
import subprocess
import json
import ast
import yaml

# Import flask modules
from flask import current_app, g

# Import caesare rest modules
from caesar_rest import oidc
from caesar_rest import mongo
from caesar_rest import utils
from caesar_rest.base_app_configurator import AppConfigurator
from caesar_rest.base_app_configurator import Option, ValueOption, EnumValueOption

# Get logger
from caesar_rest import logger

#######################################
#   CUTEX SFINDER APP CONFIGURATOR
#######################################

class CutexAppConfigurator(AppConfigurator):
	""" Class to configure CUTEX sfinder application """

	def __init__(self, app_name="cutex"):
		""" Return cutex sfinder app configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'cutex_submitter.sh'
		self.cmd_args= []
		self.batch_processing_support= True

		# - Describe app
		self.description = (
			""
		)
		
		self.tool_categories= ["image"]
		
		self.input_requirements = {
			"supported_formats": ["uid", "abspath", "dataset"],
			"expected_data": "TBD",
			"notes": [
				"TBD",
				"TBD"
			]
		}
		
		self.limitations = [
			"TBD",
			"TBD"
		]

		# - Define dictionary with allowed options
		self.valid_options= {
		

			# == COMPACT SOURCE SEARCH OPTIONS ==
			'seedthr' : ValueOption(
				name='seedthr',
				value='',
				value_type=float, 
				description='Threshold level (in nsigmas) adopted to identify sources',
				category='COMPACT-SOURCES',
				default_value=5,
				min_value=0,
				max_value=10000
			),
			'npixmin' : ValueOption(
				name='npixmin',
				value='',
				value_type=int, 
				description='Minimum number of pixels for a cluster to be significant',
				category='COMPACT-SOURCES',
				default_value=4,
				min_value=1,
				max_value=10000
			),
			'npixpsf' : ValueOption(
				name='npixpsf',
				value='',
				value_type=float, 
				description='Number of pixels that sample the instrumental PSF on the input image',
				category='COMPACT-SOURCES',
				default_value=2.7,
				min_value=1,
				max_value=10000
			),

			# == SOURCE FITTING OPTIONS ==
			'psflimmin' : ValueOption(
				name='psflimmin',
				value='',
				value_type=float, 
				description='Lower bound of the interval adopted for fitting the source size, expressed as fraction with respect to the initial/guessed source size',
				category='COMPACT-SOURCES',
				subcategory='FITTING',
				default_value=0.5,
				min_value=0.0001,
				max_value=100
			),
			'psflimmax' : ValueOption(
				name='psflimmax',
				value='',
				value_type=float, 
				description='Upper bound of the interval adopted for fitting the source size, expressed as fraction with respect to the initial/guessed source size',
				category='COMPACT-SOURCES',
				subcategory='FITTING',
				default_value=2.0,
				min_value=0.0001,
				max_value=100
			),
			
			# == RUN OPTIONS ==
			'no-logredir' : Option(
				name='no-logredir', 
				description='Do not redirect logs to output file in script',
				category='RUN'
			),
			
		} # close dict

		# - Define dictionary with job outputs produced
		self.job_outputs= {
		
		}

		# - Define option value transformers
		self.option_value_transformer= {
			
		}

		# - Fill some default cmd args
		logger.debug("Adding some options by default ...", action="submitjob")
		self.cmd_args.append("--run")
		self.cmd_args.append("--save-summaryplot")
		#self.cmd_args.append("--save-regions ")
		self.cmd_args.append("--save-catalog-to-json ")


	
	def set_data_input_option_value(self):
		""" Set app input option value """

		input_opt= "".join("--inputfile=%s" % self.data_inputs)
		self.cmd_args.append(input_opt)


	def transform_inputfile(self,file_uuid):
		""" Transform input file from uuid to actual path """		
	
		# - Get aai info
		#username= 'anonymous'
		#if ('oidc_token_info' in g) and (g.oidc_token_info is not None and 'email' in g.oidc_token_info):
		#	email= g.oidc_token_info['email']
		#	username= utils.sanitize_username(email)

		# - Get authenticated user storage identifier
		username = utils.get_storage_username()

		# - Inspect inputfile (expect it is a uuid, so convert to filename)
		logger.info("Finding inputfile uuid %s ..." % file_uuid, action="submitjob")
		collection_name= username + '.files'

		file_path= ''
		try:
			data_collection= mongo.db[collection_name]
			item= data_collection.find_one({'fileid': str(file_uuid)})
			if item and item is not None:
				file_path= item['filepath']
			else:
				logger.warn("File with uuid=%s not found in DB!" % file_uuid, action="submitjob")
				file_path= ''
		except Exception as e:
			logger.error("Exception (err=%s) catch when searching file in DB!" % str(e), action="submitjob")
			return ''
		
		if not file_path or file_path=='':
			logger.warn("inputfile uuid %s is empty or not found in the system!" % file_uuid, action="submitjob")
			return ''

		logger.info("inputfile uuid %s converted in %s ..." % (file_uuid,file_path), action="submitjob")

		return file_path
		
