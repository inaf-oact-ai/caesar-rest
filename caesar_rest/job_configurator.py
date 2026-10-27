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

from caesar_rest.app_configurators.base import AppConfigurator
from caesar_rest.app_configurators.caesar import CaesarAppConfigurator
from caesar_rest.app_configurators.mrcnn import MaskRCNNAppConfigurator
from caesar_rest.app_configurators.aegean import AegeanAppConfigurator
from caesar_rest.app_configurators.cutex import CutexAppConfigurator
from caesar_rest.app_configurators.cnn_classifier import CNNClassifierAppConfigurator
from caesar_rest.app_configurators.vit_classifier import ViTClassifierAppConfigurator
from caesar_rest.app_configurators.vit_classifier_catalog import ViTClassifierCatalogAppConfigurator
from caesar_rest.app_configurators.simclr import SimCLRFeatExtractorAppConfigurator
from caesar_rest.app_configurators.umap import UMAPAppConfigurator
from caesar_rest.app_configurators.outlier_finder import OutlierFinderAppConfigurator
from caesar_rest.app_configurators.hdbscan import HDBSCANAppConfigurator
from caesar_rest.app_configurators.simsearch import SimilaritySearchAppConfigurator
from caesar_rest.app_configurators.caesar_yolo import CaesarYoloAppConfigurator
from caesar_rest.app_configurators.sfforecaster import SFForecasterAppConfigurator
from caesar_rest.app_configurators.fextractor import FeatExtractorAppConfigurator
from caesar_rest.app_configurators.oxkat import OxkatAppConfigurator

# Get logger
from caesar_rest import logger

##############################
#   JOB CONFIGURATOR
##############################
class JobConfigurator(object):
	""" Class to configure job command """

	def __init__(self):
		""" Return a job configurator class """

		self.app_configurators= {
			'caesar': CaesarAppConfigurator,
			'aegean': AegeanAppConfigurator,
			'cutex': CutexAppConfigurator,
			'classifier-cnn': CNNClassifierAppConfigurator,
			'classifier-vit': ViTClassifierAppConfigurator,
			"classifier-vit-catalog": ViTClassifierCatalogAppConfigurator,
			'featextractor-simclr': SimCLRFeatExtractorAppConfigurator,
			'umap': UMAPAppConfigurator,
			'outlier-finder': OutlierFinderAppConfigurator,
			'hdbscan': HDBSCANAppConfigurator,
			'similarity-search': SimilaritySearchAppConfigurator,
			'caesar-mrcnn': MaskRCNNAppConfigurator,
			'caesar-yolo': CaesarYoloAppConfigurator,
			'sfforecaster': SFForecasterAppConfigurator,
			'fextractor': FeatExtractorAppConfigurator,
			'oxkat': OxkatAppConfigurator,
		}
		
		
	def validate(self, app_name, job_options, data_inputs):
		""" Validate job inputs """

		# - Validate if job inputs are valid for app
		#   Delegate validation to app configurator
		if app_name not in self.app_configurators:
			msg= 'App ' + app_name + ' not known or supported'
			logger.warn(msg, action="submitjob")
			return (None,None,msg,None)

		# - Create an instance of app configurator
		#configurator= self.app_configurators[app_name]()
		configurator= self.app_configurators[app_name](app_name=app_name)
		
		status= configurator.validate(job_options, data_inputs)
		if not status:
			status_msg= configurator.validation_status
			logger.warn("Given inputs for app %s failed to be validated!" % app_name, action="submitjob")
			return (None,None,status_msg,None)

		# - Set app cmd & cmd args
		cmd= configurator.cmd
		cmd_args= configurator.cmd_args
		if configurator.cmd_mode!="":
			cmd_args.append(configurator.cmd_mode)
		status_msg= configurator.validation_status
		run_opts= configurator.run_options		

		return (cmd,cmd_args,status_msg,run_opts)

	def get_app_description(self,app_name):
		""" Return a json dict describing given app """
		
		# - Check app name if found
		if app_name not in self.app_configurators:
			msg= 'App ' + app_name + ' not known or supported'
			logger.warn(msg, action="submitjob")
			return None

		# - Create an instance of app configurator
		#configurator= self.app_configurators[app_name]()
		configurator= self.app_configurators[app_name](app_name=app_name)

		# - Get description
		d= configurator.describe_dict()	

		return d

	def get_app_names(self):
		""" Return app names """
		
		d= {}
		app_names= []
		for app_name in self.app_configurators:
			app_names.append(app_name)
		d.update({'apps':app_names})

		#return json.loads(json.dumps(d))
		return d


	def has_batch_processing_support(self,app_name):
		""" Check if given app supports batch processing """

		# - Check app name if found
		if app_name not in self.app_configurators:
			msg= 'App ' + app_name + ' not known or supported'
			logger.warn(msg, action="submitjob")
			return None

		# - Create an instance of app configurator
		#configurator= self.app_configurators[app_name]()
		configurator= self.app_configurators[app_name](app_name=app_name)

		# - Get flag
		flag= configurator.batch_processing_support

		return flag


