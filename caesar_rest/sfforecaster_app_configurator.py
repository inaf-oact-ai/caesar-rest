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
#   SFFORECASTER APP CONFIGURATOR
##########################################

class SFForecasterAppConfigurator(AppConfigurator):
	""" Class to configure solar flare forecaster application """

	def __init__(self, app_name="sfforecaster"):
		""" Return app configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'run_forecaster.sh'
		self.cmd_args= []
		self.batch_processing_support= True
		
		# - Describe app
		self.description = (
			"Run a pre-trained forecasting model (transformer-based) on solar data with different modalities (images, videos, time-series, multi-modal) "
			"to predict the occurrence of solar flares of given types, within predefined prediction windows. "
			"The app supports different forecasting models, each specialized on specific solar data modalities and source, described below: \n\n",
			"* 'image_M+24h': Binary forecasting of M+ class flares (i.e. positive class: M/X, negative class: C/no-flares) with 24 hours prediction window from input solar magnetogram images (e.g. HMI SDO). Each image is centered on active regions, not on full disk. \n"
			"* 'video_n16_dt36m_M+24h': Binary forecasting of M+ class flares (i.e. positive class: M/X, negative class: C/no-flares) with 24 hours prediction window from input solar magnetogram videos (e.g. HMI SDO). Each video includes 16 frames, each separated by 36 minutes and centered on solar active regions, not on full disk. \n"
			"* 'video_n16_dt72m_M+24h': Binary forecasting of M+ class flares (i.e. positive class: M/X, negative class: C/no-flares) with 24 hours prediction window from input solar magnetogram videos (e.g. HMI SDO). Each video includes 16 frames, each separated by 72 minutes and centered on solar active regions, not on full disk. \n"
			"* 'ts_n1440_dt1m_M+24h': Binary forecasting of M+ class flares (i.e. positive class: M/X, negative class: C/no-flares) with 24 hours prediction window from input solar X-ray irradiance time series (e.g. NOAA GOES) including 2 time series variables:\n" 
			"    - xrs_flux_ratio: GOES XRS-B flux channel (0.1–0.8 nm), normalized to the daily background.\n"
			"    - flare_hist: set to 1 if a flare of any class occurred within a time step, and 0 otherwise.\n"
			"  Each time-series cover a time interval of 24 hours, equivalent to 1440 points at 1 min cadence.\n"
		)
		
		self.tool_categories= ["image", "video", "time-series"]
		
		self.input_requirements = {
			"supported_formats": ["fits", "png", "json", "csv"],
			"expected_data": "Single solar magnetogram image (fits/png); Single solar magnetogram images (video frames, (fits/png); Single time-series data (csv); Datalist (json) containing image/video frame/time-series data",
			"notes": [
				"The images are expected to be centred and zoomed-in on a solar active region for these forecasting models ('image_M+24h', 'video_fstep36m_M+24h', 'video_fstep72m_M+24h')"
			]
		}
		
		self.limitations = [
			"The app is for solar flare forecasting only, NOT for active region detection or SEP forecasting.",
			"Forecasting models does not support yet processing of solar full disk data, only crops around active regions.",
			"Forecasting accuracy depends on the selected pretrained model, image preprocessing, and size of the input image.",
			"The app can be used with input images from different solar regions (e.g. corona) but we anticipate sub-optimal performance as the model was trained/tested on magnetograms only."
		]
		
		# - Define dictionary with allowed options
		self.valid_options= {
		
			# == MODEL OPTIONS ==
			'model' : EnumValueOption(
				name='model',
				value='',
				value_type=str, 
				description='Forecasting model to be used. See app description.',
				category='MODEL',
				default_value='image_M+24h',
				allowed_values=['image_M+24h', 'video_n16_dt36m_M+24h', 'video_n16_dt72m_M+24h', 'ts_n1440_dt1m_M+24h']
			),
			'binary-thr' : ValueOption(
				name='binary-thr',
				value='',
				value_type=float, 
				description='Binary threshold applied to select flares (>=thr) vs non-flares (<thr)',
				category='PREPROCESSING',
				default_value=0.5,
				min_value=0.0,
				max_value=1.0
			),
			
			# == IMAGE PRE-PROCESSING OPTIONS ==
			'zscale' : Option(
				name='zscale', 
				description='Apply z-scale transform with given contrast', 
				category='PREPROCESSING',
				default_value=True
			),
			'zscale-contrast' : ValueOption(
				name='zscale-contrast',
				value='',
				value_type=float, 
				description='zscale contrast applied to all channels',
				category='PREPROCESSING',
				default_value=0.25,
				min_value=0.0,
				max_value=1.0
			),
			#'norm-min' : ValueOption(
			#	name='norm-min',
			#	value='',
			#	value_type=float, 
			#	description='Image normalization min value',
			#	category='PREPROCESSING',
			#	default_value=0.0
			#),
			#'norm-max' : ValueOption(
			#	name='norm-max',
			#	value='',
			#	value_type=float, 
			#	description='Image normalization max value',
			#	category='PREPROCESSING',
			#	default_value=1.0
			#),
			
			# == TIME-SERIES PRE-PROCESSING OPTIONS ==
			#'ts-vars': ValueOption(
			#	name='ts-vars',
			#	value='',
			#	value_type=str,
			#	description='Name of time series variables in input json data, separated by commas',
			#	category='PREPROCESSING',
			#	default_value='xrs_flux_ratio,flare_hist'
			#),
			#'ts-npoints' : ValueOption(
			#	name='ts-npoints',
			#	value='',
			#	value_type=int,	
			#	description='Number of time points in each time-series variable',
			#	category='PREPROCESSING',
			#	default_value=1440,
			#	min_value=0,
			#	max_value=100000
			#),
			#'ts-logstretchs': ValueOption(
			#	name='ts-logstretchs',
			#	value='',
			#	value_type=str,
			#	description='Log stretch TS vars separated by commas (1=enable, 0=disable). Must have same dimension of ts-vars.',
			#	category='PREPROCESSING',
			#	default_value='1,0'
			#),
    
			# == RUN OPTIONS ==
			'no-logredir' : Option(
				name='no-logredir', 
				description='Do not redirect logs to output file in script',
				category='RUN',
				default_value=False
			),
			
		
		} ## close valid options
		
		
#		{
#  "data": [
#    {
#      "sname": "05e98706da8b461e9233a7c95d4e9575",
#      "label_pred": "M+",
#     "prob_pred": 0.8321312665939331,
#      "filepath": "05e98706da8b461e9233a7c95d4e9575.png"
#    }
#  ]
#}


		# - Define dictionary with job outputs produced
		catalog_out_desc= (
			'JSON dictionary containing forecasting predicted labels (depending on forecasting model) and relative probability/confidence score. '
		)
		
		catalog_out_format= (
			'The returned dictionary follows the format below:\n\n'
			'{\n'		
			'  "filepath": "05e98706da8b461e9233a7c95d4e9575.png",\n'
			'  "sname": "05e98706da8b461e9233a7c95d4e9575",\n'
			'  "label_pred": "M+",\n'
			'  "prob_pred": 0.83\n'
			'}\n'
			'\n'
			'Below, we report a description of each dictionary field: \n'
			'* filepath | str: Input image filename (base path, not absolute path).\n'
			'* sname | str: Input image identifier, usually set to filepath without file extension.\n'
			'* label_pred | str or List[str]: Predicted forecasting class label, e.g. M+ or NONE for binary forecasting model\n'
			'* prob_pred | float or List[float]: Probability for predicted forecasting class label'
		)
		
		self.job_outputs= {
			"catalog": {
				"path": None,
				"glob": "classifier_results.json",
				"type": "application/json",
				"role": "primary_result",
				"description": catalog_out_desc,
				"format": catalog_out_format,
				"parser": "json",
				"required": True,
				"notes": (
					""
				)
			},
			"log": {
				"path": None,
				"glob": "*.log",
				"type": "text/plain",
				"role": "diagnostic",
				"description": "Execution logs.",
				"format": "",
				"parser": "text",
				"required": False,
				"notes": (
					""
				)
			}
		}
		
		# - Define option value transformers
		self.option_value_transformer= {
		
		
		} 
		
		# - Fill some default cmd args
		logger.debug("Adding some options by default ...", action="submitjob")
		self.cmd_args.append("--run")
		self.cmd_args.append("--save-base-path") # do not expose internal paths to clients
		
	def set_data_input_option_value(self):
		""" Set app input option value """

		input_opt= "".join("--inputfile=%s" % self.data_inputs)
		self.cmd_args.append(input_opt)
		
