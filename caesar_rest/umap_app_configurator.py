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
#   UMAP APP CONFIGURATOR
##########################################

class UMAPAppConfigurator(AppConfigurator):
	""" Class to configure UMAP application """

	def __init__(self, app_name="umap"):
		""" Return aapp configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'run_umap.sh'
		self.cmd_args= []
		self.batch_processing_support= True
		
		# - Describe app
		self.description = (
			"Run UMAP data dimensionality reduction tool to produce a low-dimensional embedding of a dataset (N observations, M features → K<M embedding features)."	
		)
		
		self.tool_categories= ["tabular"]
		
		input_json_format= (
			'Input JSON file has this format: \n\n'
			'{\n'
			'  "data": [\n'
			'    {\n'
			'      "sname": "f572b6faffb34f5680bccb12c02aacf5", \n'
			'      "id": "2", \n'
			'      "label": "EXTENDED", \n'
			'      "feats": [0.9604316353797913, 2.2406632900238037, 0.0, 0.0, 0.5951219797134399], \n'
			'    } \n'
			'} \n'
			'\n'
			'where: \n'
			'* sname | str: Observation identifier, usually set to filepath/uid without file extension \n'
			'* id | int or list(int): Class identifier(s) \n'
			'* label | str or list(str): Class label(s) \n'
			'* feats | list(float): Feature parameters (high-D embedding) \n'
			'Additional metadata fields specified will be preserved in the json output format.'
		)
		
		input_ascii_format= (
			'Input ascii tabular data file has this format:\n'
			'- Col 1: sname | str: Observation identifier, usually set to filepath/uid without file extension \n'
			'- Col 2,3,...,M+1: feats | float: M feature parameters (high-D embedding) for the observation \n'
			'- Col M+2: id | int or label | str: Class identifier (if int) or class label (if str) for the observation'
		)
		
		input_data_expected= input_json_format + ' \n ' + input_ascii_format
			
		self.input_requirements = {
			"supported_formats": ["json","ascii"],
			"expected_data": input_data_expected,
			"notes": [],
		}
		
		self.limitations = [
			"Low-dimensional embedding produced by UMAP significantly depends on nneighbors and mindist algorithm parameters. See parameter documentation."
		]
		
		# - Define dictionary with allowed options
		self.valid_options= {
		
			# == INPUT OPTIONS ==
			'datalist-key' : ValueOption(
				name='datalist-key',
				value='',
				value_type=str, 
				description='Dictionary key name to be read in input json datalist (default=data)',
				category='INPUT',
				default_value='data'
			),
			'selcols' : ValueOption(
				name='selcols',
				value='',
				value_type=str, 
				description='Data column indices to be selected from input data, separated by dashes. If empty, all columns are selected.',
				category='INPUT',
				default_value=''
			),
		
			# == UMAP OPTIONS ==
			'nfeats' : ValueOption(
				name='nfeats',
				value='',
				value_type=int, 
				description='Dimension of low-dimensional embedding produced by UMAP (e.g. number of output features)',
				category='PROCESSING',
				default_value=2,
				min_value=2,
				max_value=512
			),
			'mindist' : ValueOption(
				name='mindist',
				value='',
				value_type=float, 
				description='Min dist UMAP parameter. Controls compactness of clusters (how close points are allowed to get in low-D before considered fully similar). With small values (close to 0), points can pack tightly, tight/dense clusters are produced with sharper cluster separation. With high values (close to 1), points are forced to be more spread out, looser clusters are produced.',
				category='PROCESSING',
				default_value=0.1,
				min_value=0.0,
				max_value=1.0
			),
			'nneighbors' : ValueOption(
				name='nneighbors',
				value='',
				value_type=int, 
				description='N neighbors UMAP parameter. Controls how many nearby points each sample considers when defining the structure of the dataset. With small values (0-10), focus more on very local structure, producing many small clusters, sensitive to noise. With high values (>50), larger-scale structure is captured, clusters may merge, embedding looks smoother, and more global relationships appear.',
				category='PROCESSING',
				default_value=15,
				min_value=1,
				max_value=10000
			),

			# == PRE-PROCESSING OPTIONS ==
			'normalize' : Option(
				name='normalize', 
				description='If True, normalize feature data in range [0,1] before applying UMAP. If features have very different units or numerical ranges, features with larger scales will completely dominate the distance calculations, so it is suggested to normalize in that case.', 
				category='PREPROCESSING',
				default_value=True
			),
			'ids-excluded-in-train' : ValueOption(
				name='ids-excluded-in-train',
				value='',
				value_type=str, 
				description='List of observation ids (separated by colons) not included for training supervised UMAP as they are considered unknown classes (default=-1:0)',
				category='INPUT',
				default_value='-1:0'
			),
			
			# == SAVE OPTIONS ==
			'no-save-ascii' : Option(
				name='no-save-ascii', 
				description='If True, disable saving outputs to ascii format', 
				category='OUTPUT',
				default_value=False
			),
			'no-save-json' : Option(
				name='no-save-json', 
				description='If True, disable saving outputs to json format', 
				category='OUTPUT',
				default_value=False
			),
			'no-save-model' : Option(
				name='no-save-model', 
				description='If True, disable saving UMAP leaned model', 
				category='OUTPUT',
				default_value=False
			),
			'outfile-sup' : ValueOption(
				name='outfile-sup',
				value='',
				value_type=str, 
				description='Name of UMAP encoded data output file for supervised run in ascii format (default=featdata_umap_sup.dat)',
				category='OUTPUT',
				default_value='featdata_umap_sup.dat'
			),
			'outfile-unsup' : ValueOption(
				name='outfile-unsup',
				value='',
				value_type=str, 
				description='Name of UMAP encoded data output file in ascii format (default=featdata_umap.dat)',
				category='OUTPUT',
				default_value='featdata_umap.dat'
			),
			'outfile-unsup-json' : ValueOption(
				name='outfile-unsup-json',
				value='',
				value_type=str, 
				description='Name of UMAP encoded data output file in json format (default=featdata_umap.json)',
				category='OUTPUT',
				default_value='featdata_umap.json'
			),
			
			# == RUN OPTIONS ==
			'no-logredir' : Option(
				name='no-logredir', 
				description='Do not redirect logs to output file in script',
				category='RUN',
				default_value=False
			),
			'run-supervised' : Option(
				name='run-supervised', 
				description='Run UMAP also on labelled data alone (if available)',
				category='RUN',
				default_value=False
			),
			
		
		} ## close valid options
		
		# - Define dictionary with job outputs produced
		json_out_desc= (
			'JSON file containing the input data embeddings produced by UMAP in unsupervised run mode.'
		)
		
		json_out_format= (
			'Output JSON embeddings file has this format: \n\n'
			'{\n'
			'  "data": [\n'
			'    {\n'
			'      "sname": "f572b6faffb34f5680bccb12c02aacf5", \n'
			'      "id": "2", \n'
			'      "label": "EXTENDED", \n'
			'      "feats": [0.9604316353797913, 2.2406632900238037], \n'
			'    } \n'
			'} \n'
			'\n'
			'where: \n'
			'* sname | str: Observation identifier, usually set to filepath/uid without file extension \n'
			'* id | int or list(int): Class identifier(s) \n'
			'* label | str or list(str): Class label(s) \n'
			'* feats | list(float): Feature parameters produced by UMAP (low-D embeddings) \n'
			'Additional metadata fields present in the input dataset will be preserved in the json output format.'
		)
		
		ascii_out_desc= (
			'Ascii tabular file containing the input data embeddings produced by UMAP in unsupervised run mode.'
		)
		ascii_sup_out_desc= (
			'Ascii tabular file containing the input data embeddings produced by UMAP in supervised run mode.'
		)
		
		ascii_out_format= (
			'Output ascii tabular data file has this format:\n'
			'- First row: header, starting with #, e.g. # sname z1 z2 id \n'
			'- Col 1: sname | str: Observation identifier, usually set to filepath/uid without file extension \n'
			'- Col 2,3,...,M+1: feats | float: M feature parameters produced by UMAP (low-D embedding) for the observation \n'
			'- Col M+2: id | int or label | str: Class identifier (if int) or class label (if str) for the observation'
		)
				
		self.job_outputs= {
			"embeddings-json": {
				"path": None,
				"glob": "*.json",
				"type": "application/json",
				"role": "primary_result",
				"description": json_out_desc,
				"format": json_out_format,
				"parser": "json",
				"required": True,
				"notes": (
					"The embeddings json output filename produced by UMAP in unsupervised run mode is by default set to 'latent_data_umap_unsupervised.json', but it can be configured by the user with the option 'outfile-unsup-json'"
				)
			},
			"embeddings-ascii": {
				"path": None,
				"glob": "*.dat",
				"type": "text/plain",
				"role": "primary_result",
				"description": ascii_out_desc,
				"format": ascii_out_format,
				"parser": "text",
				"required": True,
				"notes": (
					"The embeddings ascii output filename produced by UMAP in unsupervised run mode is by default set to 'latent_data_umap_unsupervised.dat', but it can be configured by the user with the option 'outfile-unsup'"
				)
			},
			"embeddings-ascii-supervised": {
				"path": None,
				"glob": "*.dat",
				"type": "text/plain",
				"role": "primary_result",
				"description": ascii_sup_out_desc,
				"format": ascii_out_format,
				"parser": "text",
				"required": False,
				"notes": (
					"The embeddings ascii output filename produced by UMAP in supervised run mode is by default set to 'latent_data_umap_supervised.dat', but it can be configured by the user with the option 'outfile-sup'"
				)
			},
			"datascaler": {
				"path": None,
				"glob": "datascaler.sav",
				"type": "application/octet-stream",
				"role": "model",
				"description": "A scikit-learn data scaler used to pre-process the input data.",
				"format": "",
				"parser": "scikit-learn",
				"required": False,
				"notes": (
					""
				)
			},
			"model": {
				"path": None,
				"glob": "umap_model.sav",
				"type": "application/octet-stream",
				"role": "model",
				"description": "A scikit-learn model file including trained UMAP model.",
				"format": "",
				"parser": "scikit-learn",
				"required": False,
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
		
	def set_data_input_option_value(self):
		""" Set app input option value """

		input_opt= "".join("--inputfile=%s" % self.data_inputs)
		self.cmd_args.append(input_opt)
		
