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

##########################################
#   CNN CLASSIFIER APP CONFIGURATOR
##########################################

class CNNClassifierAppConfigurator(AppConfigurator):
	""" Class to configure CNN image classifier application """

	def __init__(self, app_name="classifier-cnn"):
		""" Return aapp configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'run_classifier.sh'
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
		
			# == MODEL OPTIONS ==
			'model' : EnumValueOption(
				name='model',
				value='',
				value_type=str, 
				description='Classifier model to be used',
				category='MODEL',
				default_value='smorphclass',
				allowed_values=['smorphclass','sclass-radio_3.4um-4.6um-12um-22um']
			),

			# == PRE-PROCESSING OPTIONS ==
			'imgsize' : ValueOption(
				name='imgsize',
				value='',
				value_type=int, 
				description='Image resize in pixels (default=64)',
				category='PREPROCESSING',
				default_value=64,
				min_value=16,
				max_value=1024
			),
			'nchannels' : ValueOption(
				name='nchannels',
				value='',
				value_type=int, 
				description='Number of channels (if -1=take from data generator). If you modify channels in preprocessing you must set this (default=-1)',
				category='PREPROCESSING',
				default_value=-1,
				min_value=-1,
				max_value=1000
			),
			'resize-chans' : Option(
				name='resize-chans', 
				description='Resize channels to desired number specified in nchan_resize', 
				category='PREPROCESSING'
			),
			'nchan-resize' : ValueOption(
				name='nchan-resize',
				value='',
				value_type=int, 
				description='Desired number of channels for resizing (default=3)',
				category='PREPROCESSING',
				default_value=3,
				min_value=1,
				max_value=1000
			),
			'normalize' : Option(
				name='normalize_minmax', 
				description='Normalize each channel in range', 
				category='PREPROCESSING'
			),
			'normmin' : ValueOption(
				name='normmin',
				value='',
				value_type=float, 
				description='Normalization min value (default=0)',
				category='PREPROCESSING',
				default_value=0.0,
				min_value=-1.0,
				max_value=0.0
			),
			'normmax' : ValueOption(
				name='normmax',
				value='',
				value_type=float, 
				description='Normalization max value (default=1)',
				category='PREPROCESSING',
				default_value=1.0,
				min_value=1.0,
				max_value=255.0
			),
			'scale-absmax' : Option(
				name='scale-absmax', 
				description='Scale to global max across all channels', 
				category='PREPROCESSING'
			),
			'scale-max' : Option(
				name='scale-max', 
				description='Scale to max not to min-max range', 
				category='PREPROCESSING'
			),
			'zscale' : Option(
				name='zscale', 
				description='Apply z-scale transform to each channel with given contrasts', 
				category='PREPROCESSING'
			),
			'zscale-contrasts' : ValueOption(
				name='zscale-contrasts',
				value='',
				value_type=str, 
				description='zscale contrasts applied to all channels, separated by commas',
				category='PREPROCESSING',
				default_value='0.25'
			),
			'sigmaclip' : Option(
				name='sigmaclip', 
				description='Apply sigma clipping to all channels', 
				category='PREPROCESSING'
			),
			'sigmaclip-low' : ValueOption(
				name='sigmaclip-low',
				value='',
				value_type=float, 
				description='Lower sigma threshold to be used for clipping pixels below (mean-sigma_low*stddev) (default=5)',
				category='PREPROCESSING',
				default_value=5.0
			),
			'sigmaclip-up' : ValueOption(
				name='sigmaclip-up',
				value='',
				value_type=float, 
				description='Upper sigma threshold to be used for clipping pixels above (mean+sigma_up*stddev) (default=30)',
				category='PREPROCESSING',
				default_value=30.0
			),
			'sigmaclip-chid' : ValueOption(
				name='sigmaclip-chid',
				value='',
				value_type=int, 
				description='Channel to clip data (-1=all) (default=-1)',
				category='PREPROCESSING',
				default_value=-1
			),
			'standardize' : Option(
				name='standardize', 
				description='Apply standardization to images', 
				category='PREPROCESSING'
			),
			'means' : ValueOption(
				name='means',
				value='',
				value_type=str, 
				description='Image means (separated by commas) to be used in standardization (default=0)',
				category='PREPROCESSING',
				default_value='0'
			),
			'sigmas' : ValueOption(
				name='sigmas',
				value='',
				value_type=str, 
				description='Image sigmas (separated by commas) to be used in standardization (default=1)',
				category='PREPROCESSING',
				default_value='1'
			),
			
			# == RUN OPTIONS ==
			'no-logredir' : Option(
				name='no-logredir', 
				description='Do not redirect logs to output file in script',
				category='RUN'
			),
			
		
		} ## close valid options
		
		# - Define dictionary with job outputs produced
		self.job_outputs= {
		
		}
		
		# - Define option value transformers
		self.option_value_transformer= {
		
		
		} 
		
		# - Fill some default cmd args
		logger.debug("Adding some options by default ...", action="submitjob")
		self.cmd_args.append("--run")
		
	def set_data_input_option_value(self):
		""" Set app input option value """

		input_opt= "".join("--inputfile=%s" % self.data_inputs)
		self.cmd_args.append(input_opt)
		
