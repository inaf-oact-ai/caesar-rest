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
#   HDBSCAN APP CONFIGURATOR
##########################################

class HDBSCANAppConfigurator(AppConfigurator):
	""" Class to configure HDBSCAN application """

	def __init__(self, app_name="hdbscan"):
		""" Return app configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'run_outlier_finder.sh'
		self.cmd_args= []
		self.batch_processing_support= True
		
		# - Describe app
		self.description = (
			"Run HDBSCAN density-based clustering algorithm to find clusters in a tabular dataset (N observations, M features)"
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
			"Returned clusters depend on the algorithm hyperparameters (min-cluster-size, min-samples, cluster-selection-epsilon).",
			"With highly dimensional data, clustering may be ineffective. Reducing the data dimensionality (e.g. PCA, UMAP, etc) could help."
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
				description='Data column indices to be selected from input data, separated by dashes. If empty, all columns are selected.',
				category='INPUT',
				default_value=''
			),
		
			# == HDBSCAN OPTIONS ==
			'min-cluster-size' : ValueOption(
				name='min-cluster-size',
				value='',
				value_type=int, 
				description='Minimum cluster size for HDBSCAN clustering (default=5)',
				category='PROCESSING',
				default_value=5,
				min_value=1,
				max_value=10000
			),
			'min-samples' : ValueOption(
				name='min-samples',
				value='',
				value_type=int, 
				description='Minimum cluster sample parameter for HDBSCAN clustering. <0 means setting it to None, which means equal to min_cluster_size (default=-1)',
				category='PROCESSING',
				default_value=-1,
				min_value=-1,
				max_value=10000
			),
			'cluster-selection-epsilon' : ValueOption(
				name='cluster-selection-epsilon',
				value='',
				value_type=float, 
				description='A distance threshold. Clusters below this value will be merged (default=0)',
				category='PROCESSING',
				default_value=0.0,
				min_value=0.0,
				max_value=10000.
			),
   		
			# == PRE-PROCESSING OPTIONS ==
			'normalize' : Option(
				name='normalize', 
				description='If True, normalize feature data in range [0,1] before applying clustering algorithm. If features have very different units or numerical ranges, features with larger scales will completely dominate the distance calculations, so it is suggested to normalize in that case.', 
				category='PREPROCESSING',
				default_value=True
			),
			'reduce-dim' : Option(
				name='reduce-dim', 
				description='Reduce feature data dimensionality before applying the clustering', 
				category='PREPROCESSING',
				default_value=False
			),
			'reduce-dim-method' : ValueOption(
				name='reduce-dim-method',
				value='',
				value_type=str, 
				description='Dimensionality reduction method {pca} (default=pca)',
				category='INPUT',
				default_value='pca'
			),
			'pca-ncomps' : ValueOption(
				name='pca-ncomps',
				value='',
				value_type=int, 
				description='Number of PCA components to be used (-1=retain all cumulating a variance above threshold) (default=-1)',
				category='PROCESSING',
				default_value=-1,
				min_value=-1,
				max_value=10000
			),
			'pca-varthr' : ValueOption(
				name='pca-varthr',
				value='',
				value_type=float, 
				description='Cumulative variance threshold used to retain PCA components (default=0.9)',
				category='PROCESSING',
				default_value=0.9,
				min_value=0.0,
				max_value=1.0
			),
			
			# == SAVE OPTIONS ==
			'no-save-ascii' : Option(
				name='no-save-ascii', 
				description='Do not save output in ascii format', 
				category='OUTPUT',
				default_value=False
			),
			'no-save-json' : Option(
				name='no-save-json', 
				description='Do not save output in json format', 
				category='OUTPUT',
				default_value=False
			),
			'no-save-model' : Option(
				name='no-save-model', 
				description='Do not save model', 
				category='OUTPUT',
				default_value=False
			),
			'no-save-features' : Option(
				name='no-save-features', 
				description='Do not save features in output files', 
				category='OUTPUT',
				default_value=False
			),
			'outfile' : ValueOption(
				name='outfile',
				value='',
				value_type=str, 
				description='Name of output file in ascii format',
				category='OUTPUT',
				default_value='clustered_data.dat'
			),
			
			'outfile-json' : ValueOption(
				name='outfile-json',
				value='',
				value_type=str, 
				description='Name of output file in json format',
				category='OUTPUT',
				default_value='clustered_data.json'
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
		json_out_desc= (
			'JSON file containing the input data with clusters identified by the algorithm.'
		)
		
		json_out_format= (
			'Output JSON file with clustering results has this format: \n\n'
			'{\n'
			'  "data": [\n'
			'    {\n'
			'      "sname": "f572b6faffb34f5680bccb12c02aacf5", \n'
			'      "id": "2", \n'
			'      "label": "EXTENDED", \n'
			'      "feats": [0.9604316353797913, 2.2406632900238037], \n'
			'      "is_outlier": 1, \n'
			'      "outlier_score": 0.78, \n'
			'    } \n'
			'} \n'
			'\n'
			'where: \n'
			'* sname | str: Observation identifier, usually set to filepath/uid without file extension \n'
			'* id | int or list(int): Class identifier(s) \n'
			'* label | str or list(str): Class label(s) \n'
			'* feats | list(float): Input feature parameters (if no-save-features option is False)\n'
			'* clust_id | int: ID of the cluster this observation belongs to. Noisy samples are set to id=-1 \n'
			'* clust_prob | float: Strength with which each observation is a member of its assigned cluster. Noise points have probability zero; points in clusters have values assigned proportional to the degree that they persist as part of the cluster \n'
			'* clust_outlier_score | float: Outlier scores for clustered points; the larger the score the more outlier-like the point \n'
			'Additional metadata fields present in the input dataset will be preserved in the json output format.'
		)
		
		ascii_out_desc= (
			'Ascii tabular file containing the input data with clusters identified by the algorithm.'
		)
		
		ascii_out_format= (
			'Output ascii tabular data file with clustering results has this format:\n'
			'- First row: header, starting with #, e.g. # sname z1 z2 id clust_id clust_prob clust_outlier_score \n'
			'- Col 1: sname | str: Observation identifier, usually set to filepath/uid without file extension \n'
			'- Col 2,3,...,M+1: feats | float: M input feature parameters for the observation (if no-save-features option is False)\n'
			'- Col M+2: id | int or label | str: Class identifier (if int) or class label (if str) for the observation \n'
			'- Col M+3: clust_id | int: ID of the cluster this observation belongs to. Noisy samples are set to id=-1 \n'
			'- Col M+4: clust_prob | float: Strength with which each observation is a member of its assigned cluster. Noise points have probability zero; points in clusters have values assigned proportional to the degree that they persist as part of the cluster \n'
			'- Col M+5: clust_outlier_score | float: Outlier scores for clustered points; the larger the score the more outlier-like the point \n'
		)

		self.job_outputs= {
			"clusters-json": {
				"path": None,
				"glob": "*.json",
				"type": "application/json",
				"role": "primary_result",
				"description": json_out_desc,
				"format": json_out_format,
				"parser": "json",
				"required": True,
				"notes": (
					"The json output filename produced is by default set to 'clustered_data.json', but it can be configured by the user with the option 'outfile-json'"
				)
			},
			"clusters-ascii": {
				"path": None,
				"glob": "*.dat",
				"type": "text/plain",
				"role": "primary_result",
				"description": ascii_out_desc,
				"format": ascii_out_format,
				"parser": "text",
				"required": True,
				"notes": (
					"The ascii output filename produced is by default set to 'clustered_data.dat', but it can be configured by the user with the option 'outfile'"
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
				"glob": "clustering_model.sav",
				"type": "application/octet-stream",
				"role": "model",
				"description": "A scikit-learn model file including clustering model.",
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
		
