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

# Import caesare rest momdules
from caesar_rest import oidc
from caesar_rest import mongo
from caesar_rest import utils
from caesar_rest.app_configurators.base_app_configurator import (
	AppConfigurator,
	Option, 
	ValueOption,
)

# Get logger
from caesar_rest import logger


##############################
#   MASK-RCNN APP CONFIGURATOR
##############################

class MaskRCNNAppConfigurator(AppConfigurator):
	""" Class to configure Mask-RCNN source finder application """

	def __init__(self, app_name="caesar-mrcnn"):
		""" Return Mask-RCNN configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.weights= current_app.config['MASKRCNN_WEIGHTS'] 
		self.cmd= 'run_mrcnn.sh --runmode=detect --weights=' + self.weights + ' '
		self.cmd_args= []
		#self.cmd_mode= ''
		self.batch_processing_support= False

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
			#'image' : ValueOption('image','',str,True, description='Path to input image (.fits) to be given to classifier (default=empty)'),
			#'weight' : ValueOption('weight','',str, description=''),
			#'classdict' : ValueOption('classdict','',str, description=''),
			'scoreThr' : ValueOption(
				name='scoreThr',
				value='',
				value_type=float, 
				description='Detected object score threshold to select as final object (default=0.7)',
				category='DETECT',
				default_value=0.7,
				min_value=0.,
				max_value=1.
			),
			'iouThr' : ValueOption(
				name='iouThr',
				value='',
				value_type=float, 
				description='IOU threshold between detected and ground truth bboxes to consider the object as detected (default=0.6)',
				category='DETECT',
				default_value=0.6,
				min_value=0.,
				max_value=1.
			),
		
		} # close dict
	
		# - Define dictionary with job outputs produced
		self.job_outputs= {
		
		}
	
		# - Define option value transformers
		#self.option_value_transformer= {
		#	'image': self.transform_imgname
		#}

	def set_data_input_option_value(self):
		""" Set app input option value """

		input_opt= "".join("--image=%s" % self.data_inputs)
		self.cmd_args.append(input_opt)


	def transform_imgname(self, file_uuid):
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
			logger.warn("imgname uuid %s is empty or not found in the system!" % file_uuid, action="submitjob")
			return ''

		return file_path

