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
#   ViT CLASSIFIER APP CONFIGURATOR
##########################################

class ViTClassifierAppConfigurator(AppConfigurator):
	""" Class to configure ViT image classifier application """

	def __init__(self, app_name="classifier-vit"):
		""" Return aapp configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'run_classifier.sh'
		self.cmd_args= []
		self.batch_processing_support= True
		
		# - Describe app
		self.description = (
			"Run a pre-trained vision transformer classifier model (ViT or ResNet-based) on radio astronomical images to predict classification labels. "
			"The app supports different classifier models, described below: \n\n",
			"* 'smorphclass_multilabel': Multi-label multi-class classification of radio images into one or more of these six possible classes: \n"
			"    - BACKGROUND: if image is purely background noise, e.g. no sources are visible, like for image frames located at the map borders\n"
			"    - RADIO-GALAXY: if any extended source is visible with a single- or multi-island morphology, suggesting that of a radio galaxy\n"
			"    - DIFFUSE: if any diffuse source is visible, typically having small-scale (e.g. <few arcmin) and roundish morphology\n"
			"    - DIFFUSE-LARGE:  if any large-scale (e.g. covering half of the image) diffuse object with irregular shape is visible\n"
			"    - ARTEFACT: if any ring-shaped or ray-like artefact is visible, e.g. typically around bright resolved source\n"
			"    This classifier aims to detect the presence of objects with a given morphology in input images with a larger field of view (~few arcmin, typically >128x128 pixels) and not on image cutouts zoomed in around a specific source.\n"
			"* 'smorphclass_singlelabel_rgz': Single-label multi-class classification of radio images into one of these six possible morphological classes: \n"
			"    - 1C-1P: single-island source having only one flux intensity peak\n"
			"    - 1C-2P: single-island source having two flux intensity peaks\n"
			"    - 1C-3P: single-island source having three flux intensity peaks\n"
			"    - 2C-2P: source formed by two disjoint islands, each hosting a single flux intensity peak\n"
			"    - 2C-3P: source formed by two disjoint islands, where one has a single flux intensity peak and the other one has two intensity peaks\n"
			"    - 3C-3P: source formed by three disjoint islands, each hosting a single flux intensity peak\n"
			"    The labelling schema is taken from the Radio Galaxy Zoo (RGZ) project, where 'C' stands for source 'components', while 'P' for 'peaks'. This classifier is intended to be run on images zoomed in around a source, typically having original size <128x128 pixels.\n"
			"* 'smorphclass_singlelabel_lotss': Single-label multi-class classification of radio galaxy images into one of these five possible morphological classes: \n"
			"    - FR-I: radio-loud galaxies characterized by a jet-dominated structure where the radio emissions are strongest close to the galaxy's center and diminish with distance from the core\n"
			"    - FR-II: radio-loud galaxies characterized by a edge-brightened radio structure, where the radio emissions are more prominent in lobes located far from the galaxy's core, with hotspots at the ends of powerful, well-collimated jets\n"
			"    - HYBRID: radio-loud galaxies exhibiting both FR-I and FR-II characteristics, typically with an FR-I-like morphology on one side of the nucleus and an FR-II-like morphology on the other\n"
			"    - SPIRAL: radio galaxies hosted by spiral galaxies, indicating the morphology of the optical host rather than the radio emission structure itself\n"
			"    - RELAXED-DOUBLE: double-lobed radio galaxies with diffuse and relatively featureless lobes, lacking strong jets or hotspots and often representing a more evolved or remnant stage of radio-source activity.\n"
			"    The labelling schema is from Horton et al, 2025 and training data from the LOFAR LoTSS survey. This classifier is intended to be run on images zoomed in around a source, typically having original size <256x256 pixels.\n"
			"* 'anomalyclass_singlelabel': Single-label multi-class classification of the peculiarity/anomaly degree of a radio astronomical image into these three possible classes: \n"
			"    - ORDINARY: image containing only point-like or slightly-resolved compact radio sources superimposed over the sky background or imaging artefact patterns; \n" 
			"    - COMPLEX: image containing one or more radio sources with extended or diffuse morphology; \n" 
			"    - PECULIAR: image containing one or more radio sources with anomalous or peculiar extended morphology, often having diffuse edges, complex irregular shapes, covering a large portion of the image.\n"
			"* 'artefactdet_singlelabel': Binary classifier, predicting if the input radio image contains one or more imaging artefact (YES) or none (NO)\n"
			"* 'radiogaldet_singlelabel': Binary classifier, predicting if the input radio image contains one or more candidate radio galaxies with extended morphology (YES) or none (NO)\n"
		)
		
		self.tool_categories= ["image"]
		
		self.input_requirements = {
			"supported_formats": ["fits", "png", "json"],
			"expected_data": "Single radio-continuum astronomical image (PNG/FITS) or JSON datalist of images",
			"notes": [
				"The image is expected to be centred and zoomed-in on a source for some classification tasks/models ('smorphclass_singlelabel_rgz', 'smorphclass_singlelabel_lotss') or having a larger field of view and including more than one source for other classification tasks ('smorphclass_multilabel', 'anomalyclass_singlelabel', 'artefactdet_singlelabel', 'radiogaldet_singlelabel')"
			]
		}
		
		self.limitations = [
			"The app is for source classification only, NOT for source detection (e.g. not providing any bounding box or segmentation mask).",
			"Classification accuracy depends on the selected pretrained model, image preprocessing, survey parameters (e.g. resolution/noise) and size of the input image.",
			"The app can be used with input images from different astronomical domains but we anticipate sub-optimal performance as the model was trained/tested on radio images only."
		]
		
		# - Define dictionary with allowed options
		self.valid_options= {
		
			# == MODEL OPTIONS ==
			'model' : EnumValueOption(
				name='model',
				value='',
				value_type=str, 
				description='Classifier model to be used. See app description.',
				category='MODEL',
				default_value='smorphclass_multilabel',
				allowed_values=['smorphclass_multilabel', 'smorphclass_singlelabel_rgz', 'smorphclass_singlelabel_lotss', 'anomalyclass_singlelabel', 'artefactdet_singlelabel', 'radiogaldet_singlelabel']
			),

			# == PRE-PROCESSING OPTIONS ==
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
				default_value=0.25
			),
			'norm-min' : ValueOption(
				name='norm-min',
				value='',
				value_type=float, 
				description='Image normalization min value',
				category='PREPROCESSING',
				default_value=0.0
			),
			'norm-max' : ValueOption(
				name='norm-max',
				value='',
				value_type=float, 
				description='Image normalization max value',
				category='PREPROCESSING',
				default_value=1.0
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
		catalog_out_desc= (
			'JSON dictionary containing image classification labels (depending on classification task/model) and relative probability/confidence score. '
		)
		
		catalog_out_format= (
			'For multi-label classification, the returned JSON dictionary follows the format below: \n\n'
			'{\n'		
			'  "filepath": "f572b6faffb34f5680bccb12c02aacf5.fits",\n'
			'  "sname": "f572b6faffb34f5680bccb12c02aacf5",\n'
			'  "label_pred": ["RADIO-GALAXY", "EXTENDED"],\n'
			'  "prob_pred": [0.606,0.754]\n'
			'}\n'
			'\n'
			'For single-label classification, the returned dictionary follows the format below:\n\n'
			'{\n'		
			'  "filepaths": "f572b6faffb34f5680bccb12c02aacf5.fits",\n'
			'  "sname": "f572b6faffb34f5680bccb12c02aacf5",\n'
			'  "label_pred": "1C-1P",\n'
			'  "prob_pred": 0.85\n'
			'}\n'
			'\n'
			'Below, we report a description of each dictionary field: \n'
			'* filepath | str: Input image filename (base path, not absolute path).\n'
			'* sname | str: Input image identifier, usually set to filepath without file extension.\n'
			'* label_pred | str or List[str]: Predicted classification label for single-label class tasks, or list of labels for multi-label class tasks\n'
			'* prob_pred | float or List[float]: Classification probability for predicted class label in single-label class tasks, or list of probabilities for each predicted label in multi-label class tasks'
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
		inputfile = self.data_inputs

		if isinstance(inputfile, list):
			if len(inputfile) != 1:
				raise ValueError(
					"classifier-vit expects exactly one input image or one JSON datalist"
				)
			inputfile = inputfile[0]

		if str(inputfile).lower().endswith(".json"):
			self.cmd_args.append("--datalist=%s" % inputfile)
		else:
			self.cmd_args.append("--inputfile=%s" % inputfile)	
		
