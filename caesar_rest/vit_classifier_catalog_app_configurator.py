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
#   ViT CATALOG CLASSIFIER APP CONFIGURATOR
##########################################

class ViTClassifierCatalogAppConfigurator(AppConfigurator):
	""" Class to configure ViT source-catalog enhancement application """

	def __init__(self, app_name="classifier-vit-catalog"):
		""" Return app configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		self.cmd = "run_classifier_on_catalog.sh"
		self.cmd_args = []
		self.batch_processing_support = False

		self.description = (
			"Run a pre-trained vision transformer classifier on source cutouts extracted "
			"from a radio astronomical image using a JSON source catalog produced by Caesar, "
			"Aegean, Caesar-YOLO, or compatible source-finding tools. "
			"The app does not classify the full input image directly (as 'vit_classifier' app does). Instead, it extracts "
			"one cutout per catalogued source, runs the selected classifier model on each cutout, "
			"and writes the classifier predictions back into the original source catalog as "
			"enhancement fields. \n"
			"The app supports different source-centric classifier models, described below: \n\n"
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
		)
		
		self.tool_categories= ["image"]

		self.input_requirements = {
			"supported_formats": {
				"image": ["fits", "png", "jpg", "jpeg"],
				"catalog": ["json"]
			},
			"expected_data": (
				"Exactly two input files are required: first the image file, then the JSON "
				"source catalog associated with that image."
			),
			"data_inputs_order": [
				"image file",
				"source catalog JSON file"
			],
			"notes": [
				"The catalog should be spatially consistent with the input image.",
				"Caesar/Aegean catalogs are usually processed at island level by default.",
				"Caesar-YOLO catalogs are processed as object-level bounding-box detections.",
				"The output is an enhanced copy of the input catalog, not a standalone image-level classifier result.",
				"The base input catalog schema is preserved; see the corresponding Caesar, Aegean, or Caesar-YOLO app output contract for the original non-enhancement fields.",
				"The app exposes only source-centric classifier models. Field-level classifiers such as anomaly, artefact, radio-galaxy detection, and multi-label scene classification are intentionally not exposed because they require larger image context. "
			]
		}

		self.limitations = [
			#"The app assumes that catalog coordinates are expressed in the same image pixel frame, or that valid WCS/RA/Dec information is available for sky-coordinate cutouts.",
			"The app extracts pixel-space cutouts around catalogued sources. The input catalog must therefore refer to the same image pixel coordinate system.",
			"The app does not perform source detection; it only classifies sources already present in the input catalog.",
			"Classification quality depends on the selected model, cutout size, source extent, image resolution, and catalog quality."
		]		

		self.valid_options = {

			# == MODEL OPTIONS ==
			"model": EnumValueOption(
				name="model",
				value="",
				value_type=str,
				description="Classifier model to be used.",
				category="MODEL",
				default_value="smorphclass_singlelabel_rgz",
				allowed_values=[
					"smorphclass_singlelabel_rgz",
					"smorphclass_singlelabel_lotss"
				]
			),

			# == CATALOG/CUTOUT OPTIONS ==
			"catalog-level": EnumValueOption(
				name="catalog-level",
				value="",
				value_type=str,
				description="Catalog level to classify for Caesar/Aegean catalogs.",
				category="CATALOG",
				default_value="auto",
				allowed_values=["auto", "source", "island", "component"]
			),
			#"coordinate-mode": EnumValueOption(
			#	name="coordinate-mode",
			#	value="",
			#	value_type=str,
			#	description="Coordinate mode used to extract cutouts.",
			#	category="CUTOUT",
			#	default_value="auto",
			#	allowed_values=["auto", "pixel", "sky"]
			#),
			#"size-mode": EnumValueOption(
			#	name="size-mode",
			#	value="",
			#	value_type=str,
			#	description="Cutout size mode.",
			#	category="CUTOUT",
			#	default_value="auto",
			#	allowed_values=["auto", "fixed", "bbox", "bbox_factor"]
			#),
			"size-mode": EnumValueOption(
				name="size-mode",
				value="",
				value_type=str,
				description="Cutout size mode. Use 'bbox' to crop around the source bounding box plus optional pixel margin, or 'bbox_factor' to scale the bounding box size by cutout-margin-factor.",
				category="CUTOUT",
				default_value="bbox_factor",
				allowed_values=["bbox", "bbox_factor"]
			),
			"cutout-size": ValueOption(
				name="cutout-size",
				value="",
				value_type=int,
				description="Minimum cutout size in pixels. When the selected bbox-based cutout is smaller than this value, it is symmetrically enlarged to at least this square size before classification.",
				category="CUTOUT",
				default_value=32,
				min_value=16,
				max_value=128
			),
			
			#"cutout-size-arcsec": ValueOption(
			#	name="cutout-size-arcsec",
			#	value="",
			#	value_type=float,
			#	description="Optional sky cutout size in arcsec when coordinate-mode is sky.",
			#	category="CUTOUT",
			#	default_value=0.0,
			#	min_value=0.0,
			#	max_value=36000.0,
			#	advanced=True
			#),
			"cutout-margin": ValueOption(
				name="cutout-margin",
				value="",
				value_type=int,
				description="Extra padding in pixels around the catalogued source bounding box. Use 0 for no additional margin.",
				category="CUTOUT",
				default_value=0,
				min_value=0,
				max_value=128
			),
			"cutout-margin-factor": ValueOption(
				name="cutout-margin-factor",
				value="",
				value_type=float,
				description="Multiplicative factor applied to the bbox-derived cutout size when size-mode='bbox_factor'. Values >1 enlarge the cutout around the source.",
				category="CUTOUT",
				default_value=1.2,
				min_value=1.0,
				max_value=2.0
			),
			#"save-cutouts": Option(
			#	name="save-cutouts",
			#	description="Save generated source cutouts for debugging.",
			#	category="CUTOUT",
			#	default_value=False,
			#	advanced=True
			#),
			"overwrite-class-fields": Option(
				name="overwrite-class-fields",
				description="Overwrite existing class/morph fields in the source catalog.",
				category="CATALOG",
				default_value=False,
				advanced=True
			),

			# == PRE-PROCESSING OPTIONS ==
			"zscale": Option(
				name="zscale",
				description="Apply z-scale transform with given contrast.",
				category="PREPROCESSING",
				default_value=True
			),
			"zscale-contrast": ValueOption(
				name="zscale-contrast",
				value="",
				value_type=float,
				description="zscale contrast applied to all channels.",
				category="PREPROCESSING",
				default_value=0.25
			),
			"norm-min": ValueOption(
				name="norm-min",
				value="",
				value_type=float,
				description="Image normalization min value.",
				category="PREPROCESSING",
				default_value=0.0
			),
			"norm-max": ValueOption(
				name="norm-max",
				value="",
				value_type=float,
				description="Image normalization max value.",
				category="PREPROCESSING",
				default_value=1.0
			),

			# == RUN OPTIONS ==
			"no-logredir": Option(
				name="no-logredir",
				description="Do not redirect logs to output file in script.",
				category="RUN",
				default_value=False
			),
		}


		# - Set job output description
		job_format=(
			"The output is a full enhanced copy of the input source catalog. The original catalog "
			"structure and original source fields are preserved. Therefore, if the input catalog is "
			"a Caesar or Aegean catalog, the output keeps the original metadata/sources/islands/"
			"fit_info/components hierarchy; if the input catalog is a Caesar-YOLO catalog, the output "
			"keeps the original filepath/sname/sources object-detection structure. The app only adds "
			"classifier enhancement fields to the catalog records that were processed.\n\n"

			"Enhancement location:\n"
			"* Caesar/Aegean catalog, catalog-level='source': fields are added to each processed top-level source record under sources[].\n"
			"* Caesar/Aegean catalog, catalog-level='island' or auto: fields are added to each processed island record under sources[].islands[]. A compact child result is also appended to the parent source record under classifier_child_results.\n"
			"* Caesar/Aegean catalog, catalog-level='component': fields are added to each processed component record under sources[].islands[].fit_info.components[]. A compact child result is also appended to the parent source record and island record under classifier_child_results.\n"
			"* Caesar-YOLO catalog: fields are added directly to each processed object record under sources[].\n\n"

			"Fields added to each directly classified record:\n"
			"* classification_info | dict: Complete classifier enhancement block. Contains model, label_schema, multilabel, binary, level, label_pred, prob_pred, all_probs, and cutout.\n"
			"* classifier_label | str: Primary predicted class label. For the exposed catalog models this is usually one of the selected source-centric morphology classes.\n"
			"* classifier_score | float: Confidence/probability associated with classifier_label.\n"
			"* classifier_labels | str or List[str]: Raw predicted label value returned by the classifier. For single-label models this is a string; for multi-label-compatible runners this may be a list.\n"
			"* classifier_probs | float or List[float]: Raw probability value(s) associated with classifier_labels.\n"
			"* classifier_all_probs | dict: Mapping from every model class label to its probability score.\n"
			"* tags | List[str]: Existing tag list updated with the predicted classifier label when not already present.\n\n"

			"classification_info fields:\n"
			"* model | str: Model path/name used internally by the container.\n"
			"* label_schema | str: Label schema used by the classifier runner.\n"
			"* multilabel | bool: Whether the classifier was run in multi-label mode.\n"
			"* binary | bool: Whether the classifier was run in binary mode.\n"
			"* level | str: Normalized catalog level classified by the runner, e.g. source, island, component, or object.\n"
			"* label_pred | str or List[str]: Raw classifier prediction.\n"
			"* prob_pred | float or List[float]: Raw classifier confidence value(s).\n"
			"* all_probs | dict: Probability for all model classes.\n"
			"* cutout | dict: Information on the extracted source cutout used for inference.\n\n"

			"cutout fields:\n"
			"* coordinate_mode | str: Coordinate system used for cutout extraction. The current app always uses 'pixel'.\n"
			"* center_source | str: Method used to determine the cutout center (e.g. centroid, bbox_center).\n"
			"* center_pixel | dict: Pixel coordinates of the cutout center.\n"
			"* bounds_original | List[int]: Bounding box of the extracted cutout in the original image pixel frame, reported as [xmin, xmax, ymin, ymax].\n"
			"* size_pixels | List[int]: Actual cutout dimensions after clipping to the image boundaries.\n"
			"* size_pixels_requested | int: Requested pixel cutout size after applying size-mode, minimum cutout size, bbox scaling, and margin.\n\n"
			
			"Fields added to parent records when child-level objects are classified:\n"
			"* classifier_child_results | List[dict]: List of compact child classifier results propagated from classified islands/components. Each entry contains the classifier prediction block plus child_level and child_name. This does not imply that the parent itself was independently classified.\n\n"

			"Top-level summary fields:\n"
			"* classifier_summary | dict: Execution summary with status, n_sources_normalized, n_sources_classified, n_sources_skipped, results, and skipped.\n"
			"* metadata.sclassifier_vit_catalog_enhancement | dict: Run metadata including inputfile, catalogfile, model, label_schema, catalog_level, size_mode, minimum cutout size, cutout margin, cutout margin factor, and processed/skipped counters."
		)

		self.job_outputs = {
			"catalog": {
				"path": None,
				"glob": "classifier_catalog_results.json",
				"type": "application/json",
				"role": "primary_result",
				"description": "Enhanced source catalog JSON with classifier predictions added to catalogued sources.",
				"format": job_format,
				"parser": "json",
				"required": True,
				"notes": (
					"This output is the authoritative enhanced catalog. The classifier_summary field "
					"contains compact execution counters and previews, but the source-level classifier "
					"information is stored inside the catalog records themselves."
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
				"notes": ""
			}
		}

		self.option_value_transformer = {}

		logger.debug("Adding some options by default ...", action="submitjob")
		self.cmd_args.append("--run")
		self.cmd_args.append("--save-base-path")
		self.cmd_args.append("--coordinate-mode=pixel") # force coordinate mode=pixel

	def validate(self, job_options, data_inputs):
		""" Validate app inputs before generic option validation """

		if not isinstance(data_inputs, list) or len(data_inputs) != 2:
			self.validation_status = (
				"classifier-vit-catalog expects exactly two data inputs: "
				"image file first, source catalog JSON file second."
			)
			logger.warn(self.validation_status, action="submitjob")
			return False

		return AppConfigurator.validate(self, job_options, data_inputs)

	def set_data_input_option_value(self):
		""" Set image and catalog input option values """

		image_path = self.data_inputs[0]
		catalog_path = self.data_inputs[1]

		self.cmd_args.append("--inputfile=%s" % image_path)
		self.cmd_args.append("--catalogfile=%s" % catalog_path)
