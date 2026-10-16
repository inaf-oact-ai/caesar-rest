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
#   CAESAR-YOLO APP CONFIGURATOR
##########################################

class CaesarYoloAppConfigurator(AppConfigurator):
	""" Class to configure caesar-yolo source finder application """

	def __init__(self, app_name="caesar-yolo"):
		""" Return app configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'run_sdetector.sh'
		self.cmd_args= []
		self.batch_processing_support= True
		
		# - Describe app
		self.description = (
			"Run a pre-trained YOLO object detection model on radio astronomical images to DETECT candidate radio sources and also CLASSIFY them in the following morphological classes: \n",
			"- 'SPURIOUS': imaging artefacts, usually found around bright sources and with a ring-like or elongated compact morphology;\n",
			"- 'COMPACT': single-island isolated point- or slightly resolved compact radio sources, eventually hosting one or more blended components, each with morphology resembling the synthesized beam shape;\n"
			"- 'EXTENDED': radio sources with a single-island extended morphology, eventually hosting one or more blended components, with some deviating from the synthesized beam shape;\n"
			"- 'EXTENDED-MULTISLAND': radio sources with an extended morphology, consisting of more (point-like or extended) islands, each one eventually hosting one or more blended components;\n"
			"- 'FLAGGED': single-island bright radio sources, with compact or extended morphology, that are poorly imaged and cannot be separated from close imaging artefacts.\n"		
			#"The app expects input image-like astronomical data, in either FITS or PNG format. "
			#"Results are returned as a JSON catalog of detections and optional diagnostic plots."
		)
		
		self.tool_categories= ["image"]
		
		self.input_requirements = {
			"supported_formats": ["fits", "png"],
			"expected_data": "Single radio-continuum astronomical image",
			"notes": [],
		}

		self.limitations = [
			"Source detection accuracy depends on the selected pretrained model, image preprocessing, survey parameters (e.g. resolution/noise) of the input image, and detection parameters choices ('score-thr', 'iou-thr').",
			#"For better detection performance, set model and imgsize to the same value (e.g. yolov11l_imgsize640, imgsize=640), as closest as possible to original input image size.",
			"For best detection performance, use the imgsize associated with the selected pretrained model (e.g. yolov11l_imgsize256 with imgsize=256). Model/input-size selection should follow the training configuration of the pretrained model rather than simply choosing the size closest to the original image dimensions.",
			"Processing of very large images (>1024 pixels) is supported but it requires enabling the tiling and parallel run mode (see options).",
			"The app can be used with input images from different astronomical domains (e.g. infrared) but we anticipate sub-optimal performance as the model was trained/tested on radio images only."
		]
		
		# - Define dictionary with allowed options
		self.valid_options= {
		
			# == MODEL OPTIONS ==
			'model' : EnumValueOption(
				name='model',
				value='',
				value_type=str, 
				description='Pretrained model to be used in prediction',
				category='MODEL',
				default_value='yolov11l_imgsize640',
				allowed_values=['yolov11l_imgsize128','yolov11l_imgsize256','yolov11l_imgsize512','yolov11l_imgsize640', 'yolov11l_imgsize1024']
			),

			# == PRE-PROCESSING OPTIONS ==
			'xmin' : ValueOption(
				name='xmin',
				value='',
				value_type=int, 
				description='Read sub-image of input image starting from pixel x=xmin (-1: read full image)',
				category='IMGREAD',
				default_value=-1,
				min_value=-1000000,
				max_value=1000000
			),
			'xmax' : ValueOption(
				name='xmax',
				value='',
				value_type=int, 
				description='Read sub-image of input image up to pixel x=xmax (-1: read full image)',
				category='IMGREAD',	
				default_value=-1,
				min_value=-1000000,
				max_value=1000000
			),
			'ymin' : ValueOption(
				name='ymin',
				value='',
				value_type=int, 
				description='Read sub-image of input image starting from pixel y=xmin (-1: read full image)',
				category='IMGREAD',	
				default_value=-1,
				min_value=-1000000,
				max_value=1000000
			),
			'ymax' : ValueOption(
				name='ymax',
				value='',
				value_type=int, 
				description='Read sub-image of input image up to pixel y=ymax (-1: read full image)',
				category='IMGREAD',
				default_value=-1,
				min_value=-1000000,
				max_value=1000000
			),
			'imgsize' : ValueOption(
				name='imgsize',
				value='',
				value_type=int, 
				description='Image resize in pixels',
				category='PREPROCESSING',
				default_value=640,
				min_value=16,
				max_value=1024
			),
			'preprocessing' : Option(
				name='preprocessing', 
				description='Apply pre-processing to input image',
				category='PREPROCESSING',
				default_value=True
			),
			'normalize' : Option(
				name='normalize', 
				description='Normalize each channel in range', 
				category='PREPROCESSING',
				default_value=True
			),
			'norm-min' : ValueOption(
				name='norm-min',
				value='',
				value_type=float, 
				description='Normalization min value',
				category='PREPROCESSING',
				default_value=0.0,
				min_value=-1.0,
				max_value=0.0
			),
			'norm-max' : ValueOption(
				name='norm-max',
				value='',
				value_type=float, 
				description='Normalization max value',
				category='PREPROCESSING',
				default_value=255.0,
				min_value=1.0,
				max_value=255.0
			),
			'subtract-bkg' : Option(
				name='subtract-bkg', 
				description='Subtract bkg from ref channel image', 
				category='PREPROCESSING',
				default_value=False
			),
			'sigma-bkg' : ValueOption(
				name='sigma-bkg',
				value='',
				value_type=float, 
				description='Sigma clip to be used in bkg calculation',
				category='PREPROCESSING',
				default_value=3.0,
				min_value=1.0,
				max_value=100.0
			),
			'use-box-mask-in-bkg' : Option(
				name='use-box-mask-in-bkg', 
				description='Compute bkg value in borders left from box mask', 
				category='PREPROCESSING',
				default_value=False
			),
			'bkg-box-mask-fract' : ValueOption(
				name='bkg-box-mask-fract',
				value='',
				value_type=float, 
				description='Size of mask box dimensions with respect to image size used in bkg calculation',
				category='PREPROCESSING',
				default_value=0.7,
				min_value=0.0001,
				max_value=1.0
			),
			'bkg-chid' : ValueOption(
				name='bkg-chid',
				value='',
				value_type=int, 
				description='Channel to subtract background (-1=all)',
				category='PREPROCESSING',
				default_value=-1,
				min_value=-1,
				max_value=3
			),
			'clipshiftdata' : Option(
				name='clipshiftdata', 
				description='Do sigma clipping shifting', 
				category='PREPROCESSING',
				default_value=False
			),
			'sigmaclip' : ValueOption(
				name='sigmaclip',
				value='',
				value_type=float, 
				description='Sigma threshold to be used for clip & shifting pixels',
				category='PREPROCESSING',
				default_value=1.0,
				min_value=0.001,
				max_value=100
			),
			'clipdata' : Option(
				name='clipdata', 
				description='Apply sigma clipping to all channels', 
				category='PREPROCESSING',
				default_value=False
			),
			'sigmaclip-low' : ValueOption(
				name='sigmaclip-low',
				value='',
				value_type=float, 
				description='Lower sigma threshold to be used for clipping pixels below (mean-sigma_low*stddev)',
				category='PREPROCESSING',
				default_value=10.0,
				min_value=0.001,
				max_value=100
			),
			'sigmaclip-up' : ValueOption(
				name='sigmaclip-up',
				value='',
				value_type=float, 
				description='Upper sigma threshold to be used for clipping pixels above (mean+sigma_up*stddev)',
				category='PREPROCESSING',
				default_value=10.0,
				min_value=0.001,
				max_value=100
			),
			'sigmaclip-chid' : ValueOption(
				name='sigmaclip-chid',
				value='',
				value_type=int, 
				description='Channel to clip data (-1=all)',
				category='PREPROCESSING',
				default_value=-1,
				min_value=-1,
				max_value=3
			),		
			'zscale' : Option(
				name='zscale', 
				description='Apply z-scale transform to each channel with given contrasts', 
				category='PREPROCESSING',
				default_value=True
			),
			'zscale-contrasts' : ValueOption(
				name='zscale-contrasts',
				value='',
				value_type=str, 
				description='zscale contrasts applied to all channels, separated by colons',
				category='PREPROCESSING',
				default_value='0.25:0.25:0.25'
			),
			'chan3-preproc' : Option(
				name='chan3-preproc', 
				description='Use the 3-channel pre-processor', 
				category='PREPROCESSING',
				default_value=False
			),
			'sigmaclip-baseline' : ValueOption(
				name='sigmaclip-baseline',
				value='',
				value_type=float, 
				description='Lower sigma threshold to be used for clipping pixels below (mean-sigma_low*stddev) in first channel of 3-channel preprocessing',
				category='PREPROCESSING',
				default_value=0.0
			),
			'nchans' : ValueOption(
				name='nchans',
				value='',
				value_type=int, 
				description='Number of channels. If you modify channels in preprocessing you must set this accordingly',
				category='PREPROCESSING',
				default_value=1,
				min_value=1,
				max_value=3
			),
			
			# == DETECT OPTIONS ==
			'score-thr' : ValueOption(
				name='score-thr',
				value='',
				value_type=float, 
				description='Object detection score threshold to be used during test. Low value: higher recall, lower precision. High value: lower recall, higher precision.',
				category='DETECT',
				default_value=0.5,
				min_value=0.0,
				max_value=1.0
			),
			'iou-thr' : ValueOption(
				name='iou-thr',
				value='',
				value_type=float, 
				description='Intersection Over Union (IoU) threshold for Non-Maximum Suppression (NMS)',
				category='DETECT',
				default_value=0.5,
				min_value=0.0,
				max_value=1.0
			),
			'merge-overlap-iou-thr-soft' : ValueOption(
				name='merge-overlap-iou-thr-soft',
				value='',
				value_type=float, 
				description='IOU threshold used to merge overlapping detected objects with same class ',
				category='DETECT',
				default_value=0.3,
				min_value=0.0,
				max_value=1.0
			),
			'merge-overlap-iou-thr-hard' : ValueOption(
				name='merge-overlap-iou-thr-hard',
				value='',
				value_type=float, 
				description='IOU threshold used to merge overlapping detected objects, even those with same class ',
				category='DETECT',
				default_value=0.8,
				min_value=0.0,
				max_value=1.0
			),
	
			# == PARALLEL RUN OPTIONS ==
			'split-img-in-tiles' : Option(
				name='split-img-in-tiles', 
				description='Split input image in multiple sub tiles', 
				category='PARALLEL-RUN',
				default_value=False
			),
			'tile-xsize' : ValueOption(
				name='tile-xsize',
				value='',
				value_type=int, 
				description='Sub image size in pixel along x',
				category='PARALLEL-RUN',
				default_value=512,
				min_value=16,
				max_value=1024
			),
			'tile-ysize' : ValueOption(
				name='tile-ysize',
				value='',
				value_type=int, 
				description='Sub image size in pixel along y',
				category='PARALLEL-RUN',
				default_value=512,
				min_value=16,
				max_value=1024
			),
			'tile-xstep' : ValueOption(
				name='tile-xstep',
				value='',
				value_type=float, 
				description='Sub image step fraction along x (=1 means no overlap)',
				category='PARALLEL-RUN',
				default_value=1.0,
				min_value=0.0,
				max_value=1.0
			),
			'tile-ystep' : ValueOption(
				name='tile-ystep',
				value='',
				value_type=float, 
				description='Sub image step fraction along y (=1 means no overlap)',
				category='PARALLEL-RUN',
				default_value=1.0,
				min_value=0.0,
				max_value=1.0
			),
			'max-ntasks-per-worker' : ValueOption(
				name='max-ntasks-per-worker',
				value='',
				value_type=int, 
				description='Max number of tasks assigned to a MPI processor worker',
				category='PARALLEL-RUN',
				default_value=100,
				min_value=1,
				max_value=200
			),
	
			# == DRAW OPTIONS ==
			'draw-plots' : Option(
				name='draw-plots', 
				description='Enable plot making', 
				category='DRAW',
				default_value=False
			),
			'draw-class-label-in-caption' : Option(
				name='draw-class-label-in-caption', 
				description='Enable drawing of class label in plots', 
				category='DRAW',
				default_value=True
			),
	
			# == SAVE OPTIONS ==
			'save-plots' : Option(
				name='save-plots', 
				description='Enable plot saving', 
				category='SAVE',
				default_value=True
			),
			'save-tile-catalog' : Option(
				name='save-tile-catalog', 
				description='Enable saving of subtile catalog files', 
				category='SAVE',
				default_value=False
			),
			'save-tile-region' : Option(
				name='save-tile-region', 
				description='Enable saving of subtile DS9 region files', 
				category='SAVE',
				default_value=False
			),
			'save-tile-img' : Option(
				name='save-tile-img', 
				description='Enable saving of subtile image files', 
				category='SAVE',
				default_value=False
			),
			'outfile-plot' : ValueOption(
				name='outfile-plot',
				value='',
				value_type=str, 
				description='Output plot PNG filename (internally generated if left empty)',
				category='SAVE',
				default_value='plot.png'
			),
			'outfile-catalog' : ValueOption(
				name='outfile-catalog',
				value='',
				value_type=str, 
				description='Output json filename with detected objects (internally generated if left empty for --image option)',
				category='SAVE',
				default_value='catalog.json'
			),
			'outfile-region' : ValueOption(
				name='outfile-region',
				value='',
				value_type=str, 
				description='Output DS9 region filename (internally generated if left empty)',
				category='SAVE',
				default_value='ds9.reg'
			),
	
			# == RUN OPTIONS ==
			'no-logredir' : Option(
				name='no-logredir', 
				description='Do not redirect logs to output file in run script. If True, no log file produced and returned as output product (only internal Slurm log)',
				category='RUN',
				default_value=False
			),
			
		} ## close valid options
		
		
		# - Define dictionary with job outputs produced
		catalog_out_desc= (
			'JSON dictionary containing list of detected objects/sources with class labels, confidence scores, bounding-box rectangle coordinates and various flags.'
		)
		
		catalog_out_format= (
			'JSON dictionary follows the format below: \n\n'
			'{\n'
			'  "filepath": "f572b6faffb34f5680bccb12c02aacf5.fits", \n'
			'  "sname": "f572b6faffb34f5680bccb12c02aacf5", \n'
			'  "sources": [ \n'
			'    { \n'
			'      "class_id": 3, \n'
			'      "class_name": "extended-multisland", \n'
			'      "edge": 0, \n'
			'      "name": "S1", \n'
			'      "score": 0.8755874037742615, \n'
			'      "x1": 27.0, \n'
			'      "x2": 114.0, \n'
			'      "y1": 39.0, \n'
			'      "y2": 96.0 \n'
			'    } \n'
			'  ] \n'
			'} \n'
			'\n'
			'where: \n'
			'* filepath | str: Input image filename (base path, not absolute path).\n'
			'* sname | str: Input image identifier, usually set to filepath without file extension.\n'
			'* sources | list(dict): List of detected object parameters, where each object dictionary contains the following information:\n'
			'      - class_id | int: Object class identifier with these possible values: 0-->spurious, 1-->compact, 2-->extended, 3-->extended-multisland, 4-->flagged\n'
			'      - class_name | str: Object class label with these possible values: spurious, compact, extended, extended-multisland, flagged\n'
			'      - edge | int: Boolean flag indicating if the detected source is at the border (=1) of the image or not (=0)\n'
			'      - merged | int: Boolean flag indicating if the detected source was assembled from connected objects detected at the border of adjacent image tiles (=1) or not (=0). This flag is only set in parallel runs where the input image is partitioned into sub-tiles.\n'
			'      - name | str: A string identifier for the detected object, usually with an "S" prefix followed by an integer\n'
			'      - score | float: Object detection confidence probability in range [0,1] \n'
			'      - x1 | float: Minimum x-value of the object bounding box rectangle in image coordinates\n'
			'      - x2 | float: Maximum x-value of the object bounding box rectangle in image coordinates\n'
			'      - y1 | float: Minimum y-value of the object bounding box rectangle in image coordinates\n'
			'      - y2 | float: Maximum y-value of the object bounding box rectangle in image coordinates'
		)
				
		self.job_outputs= {
			"catalog": {
				"path": None,
				"glob": "*.json",
				"type": "application/json",
				"role": "primary_result",
				"description": catalog_out_desc,
				"format": catalog_out_format,
				"parser": "json",
				"required": True,
				"notes": (
					"The catalog output filename is by default set to 'catalog.json', but it can be configured by the user with the option 'outfile-catalog'"
				)
			},
			"plot": {
				"path": None,
				"glob": "*.png",
				"type": "image/png",
				"role": "visualization",
				"description": "Image with detections overlaid.",
				"format": "",
				"parser": "image",
				"required": False,
				"notes": (
					"The plot output filename is by default set to 'plot.png', but it can be configured by the user with the option 'outfile-plot'"
				)
			},
			"region": {
				"path": None,
				"glob": "*.reg",
				"type": "application/x-ds9",
				"role": "visualization",
				"description": "A DS9 region file containing detected sources as colored and tagged box regions.",
				"format": "",
				"parser": "ds9",
				"required": False,
				"notes": (
					"The region output filename is by default set to 'ds9.reg', but it can be configured by the user with the option 'outfile-region'"
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
		
		} ## close job outputs
		
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
		
	
