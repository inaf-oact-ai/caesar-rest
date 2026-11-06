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
from caesar_rest.app_configurators.base import (
	AppConfigurator,
	Option, 
	ValueOption, 
	EnumValueOption,
)

# Get logger
from caesar_rest import logger

##########################################
#   SimilaritySearch APP CONFIGURATOR
##########################################

class SimilaritySearchAppConfigurator(AppConfigurator):
	""" Class to configure Similarity Search application """

	def __init__(self, app_name="similarity-search"):
		""" Return app configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'run_simsearch.sh'
		self.cmd_args= []
		self.batch_processing_support= True
		
		# - Describe app
		
		# - Describe app
		self.description = (
			"Search for similar images using nearest-neighbor retrieval "
			"on numerical feature vectors and the Faiss library. "
			"Two workflows are supported: nearest-neighbor retrieval "
			"within a feature dataset, and retrieval of dataset images "
			"most similar to an input query image. "
			"The query-image workflow uses a compatible pretrained "
			"feature extraction model to compute the query embedding."
		)

		self.tool_categories = ["image", "tabular"]

		self.input_requirements = {
			"supported_formats": ["json", "ascii", "fits", "png"],
			"expected_data": (
				"A feature dataset containing numerical embedding "
				"vectors for the indexed observations. JSON input "
				"contains a data array with observation metadata "
				"and a feats array of numerical feature values. "
				"For query-image search, provide a second input "
				"containing the image to compare against the dataset."
			),
			"notes": [
				"One input executes nearest-neighbor retrieval within "
				"the supplied feature dataset.",
				"Two inputs execute query-image retrieval. The first "
				"input is the feature dataset and the second is the "
				"query image.",
				"Feature vectors must be compatible with the selected "
				"feature extraction model and preprocessing.",
				"CAESAR-REST data reference types such as uid and "
				"dataset are distinct from scientific file formats."
			]
		}

		self.limitations = [
			"Similarity depends on the feature representation, "
			"preprocessing and training data of the selected model.",
			"High similarity does not necessarily imply identical "
			"scientific properties or morphological classifications.",
			"Query-image and indexed feature vectors must have "
			"compatible dimensions and representation semantics.",
			"Approximate nearest-neighbor search may trade retrieval "
			"accuracy for computational performance.",
			"Model availability depends on the installed scientific "
			"container."
		]
		
		# - Define dictionary with allowed options
		self.valid_options= {
		
			# == INPUT OPTIONS ==
			'datalist-key' : ValueOption(
				name='datalist-key',
				value='',
				value_type=str, 
				description='Dictionary key name to be read in input datalist (default=data)',
				category='INPUT',
				default_value='data'
			),
			'selcols' : ValueOption(
				name='selcols',
				value='',
				value_type=str, 
				description='Data column ids to be selected from input data, separated by commas (default=all columns)',
				category='INPUT',
				default_value=''
			),
		
			# == FEATURE EXTRACTION OPTIONS ==
			'model' : EnumValueOption(
				name='model',
				value='',
				value_type=str, 
				description='Feature extractor model to be used',
				category='MODEL',
				default_value='simclr-smgps',
				#allowed_values=['hulk-smgps','hulk-emupilot','banner-smgps','banner-emupilot']
				allowed_values=['simclr-smgps']
			),
			
			# == SIMILARITY SCAN OPTIONS ==
			'k' : ValueOption(
				name='k',
				value='',
				value_type=int, 
				description='Number of neighbors in similarity search (default=10)',
				category='PROCESSING',
				default_value=10,
				min_value=1,
				max_value=100000
			),
			'score-thr' : ValueOption(
				name='score-thr',
				value='',
				value_type=float, 
				description='Similarity threshold below which neighbors are not include in graph (default=0.0)',
				category='PREPROCESSING',
				default_value=0.0,
				min_value=0.0,
				max_value=1.0
			),
			'large-data-thr' : ValueOption(
				name='large-data-thr',
				value='',
				value_type=int, 
				description='Number of data entries above which an approximate search algorithm is used (default=1000000)',
				category='PROCESSING',
				default_value=1000000,
				min_value=1,
				max_value=1000000
			),
			'nlist' : ValueOption(
				name='nlist',
				value='',
				value_type=int, 
				description='The number of clusters (inverted lists) for the IVFPQ index (default=100)',
				category='PROCESSING',
				default_value=100,
				min_value=1,
				max_value=100000
			),
			'M' : ValueOption(
				name='M',
				value='',
				value_type=int, 
				description='The number of sub-quantizers in Product Quantization (default=8)',
				category='PROCESSING',
				default_value=8,
				min_value=1,
				max_value=100000
			),
			'nprobe' : ValueOption(
				name='nprobe',
				value='',
				value_type=int, 
				description='The number of clusters to visit during search. Larger nprobe = better recall but slower (default=10)',
				category='PROCESSING',
				default_value=10,
				min_value=1,
				max_value=100000
			),
			   		
			# == PRE-PROCESSING OPTIONS ==
			'imgsize' : ValueOption(
				name='imgsize',
				value='',
				value_type=int, 
				description='Image resize size in pixels (default=224)',
				category='PROCESSING',
				default_value=224,
				min_value=8,
				max_value=1024
			),
			'zscale' : Option(
				name='zscale', 
				description='Apply zscale transform', 
				category='PREPROCESSING',
				default_value=False
			),
			'zscale-contrast' : ValueOption(
				name='zscale-contrast',
				value='',
				value_type=float, 
				description='ZScale transform contrast (default=0.25)',
				category='PREPROCESSING',
				default_value=0.25,
				min_value=0.0,
				max_value=1.0
			),
			
			# == SAVE OPTIONS ==
			'outfile' : ValueOption(
				name='outfile',
				value='',
				value_type=str, 
				description='Output filename (.json) of feature data with similarity search info (default=featdata_simsearch.json)',
				category='OUTPUT',
				default_value='featdata_simsearch.json'
			),
			
			# == RUN OPTIONS ==
			'no-logredir' : Option(
				name='no-logredir', 
				description='Do not redirect logs to output file in script',
				category='RUN',
				default_value=False
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

		# - Check if multiple inputs are given
		if isinstance(self.data_inputs, list):
			inputfile= self.data_inputs[0]
			if len(self.data_inputs)==1:
				inputfile= self.data_inputs[0]
				input_opt= "".join("--inputfile=%s" % inputfile)
			elif len(self.data_inputs)==2:
				imgfile= self.data_inputs[1]
				input_opt= "".join("--inputfile=%s --img=%s" % (inputfile, imgfile))
		else:
			inputfile= self.data_inputs
			input_opt= "".join("--inputfile=%s" % inputfile)
		
		self.cmd_args.append(input_opt)
		
