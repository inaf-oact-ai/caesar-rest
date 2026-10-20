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
from caesar_rest.app_configurators.base_app_configurator import (
	AppConfigurator,
	Option, 
	ValueOption, 
	EnumValueOption,
)

# Get logger
from caesar_rest import logger

#######################################
#   AEGEAN SFINDER APP CONFIGURATOR
#######################################

class AegeanAppConfigurator(AppConfigurator):
	""" Class to configure AEGEAN sfinder application """

	def __init__(self, app_name="aegean"):
		""" Return aegean sfinder app configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'aegean_submitter.sh'
		self.cmd_args= []
		self.batch_processing_support= True

		# - Describe app
		self.description = (
			"Run Aegean source finder tool on radio astronomical images to extract point-like/compact sources. "
			"The tool also supports characterization of extracted compact sources, including component identification and measurement of source/component parameters (flux density, position, extension) through 2D gaussian mixture fitting. "
		)
		
		self.tool_categories= ["image"]
		
		self.input_requirements = {
			"expected_data": "Single radio-continuum astronomical image",
			"supported_formats": ["fits"],
			"notes": [],
		}
		
		self.limitations = [
			"Compact source detection accuracy depends on background estimation parameters and detection thresholds.",
			"Processing of very large images (>10000 pixels) is in principle supported but it may be computationally expensive. No parallel run mode is provided."
			"The app can be used with input images from different astronomical domains (e.g. infrared) but we anticipate sub-optimal performance as the tool was specifically tested on radio images and relative image metadata only."
		]

		# - Define dictionary with allowed options
		self.valid_options= {
			
			# == OUTPUT OPTIONS ==
			'save-bkgmap' : Option(
				name='save-bkgmap', 
				description='Save bkg map in output file', 
				category='OUTPUT',
				default_value=False
			),
			'save-rmsmap' : Option(
				name='save-rmsmap', 
				description='Save rms map in output file', 
				category='OUTPUT',
				default_value=False
			),

			# == BKG OPTIONS ==
			'bkgbox' : ValueOption(
				name='bkgbox',
				value='',
				value_type=int, 
				description='Box size in pixels used to compute local bkg (default: 5*grid if not given)',
				category='IMGBKG',
				default_value=100,
				min_value=5,
				max_value=10000
			),
			'bkggrid' : ValueOption(
				name='bkggrid',
				value='',
				value_type=int, 
				description='Grid size in pixels used to compute local bkg (default: ~4* beam size square if not given)',
				category='IMGBKG',
				default_value=20,
				min_value=5,
				max_value=1000
			),
			
			# == COMPACT SOURCE SEARCH OPTIONS ==
			'seedthr' : ValueOption(
				name='seedthr',
				value='',
				value_type=float, 
				description='Seed threshold (in nsigmas) used in flood-fill algo',
				category='COMPACT-SOURCES',
				default_value=5,
				min_value=0,
				max_value=10000
			),
			'mergethr' : ValueOption(
				name='mergethr',
				value='',
				value_type=float, 
				description='Merge threshold (in nsigmas) used in flood-fill algo',
				category='COMPACT-SOURCES',
				default_value=2.6,
				min_value=0,
				max_value=10000
			),
			
			# == SOURCE FITTING OPTIONS ==
			'fit-maxcomponents' : ValueOption(
				name='fit-maxcomponents',
				value='',
				value_type=int, 
				description='Maximum number of components fitted in a blob',
				category='COMPACT-SOURCES',
				subcategory='FITTING',
				default_value=3,
				min_value=0,
				max_value=100
			),
			
			# == RUN OPTIONS ==
			'no-logredir' : Option(
				name='no-logredir', 
				description='Do not redirect logs to output file in script',
				category='RUN',
				default_value=False
			),
			'ncores' : ValueOption(
				name='ncores',
				value='',
				value_type=int, 
				description='Number of cores to be used in BANE/aegean',
				category='RUN',
				default_value=1,
				min_value=1,
				max_value=100
			),
			
		} # close dict

		# - Define dictionary with job outputs produced
		json_catalog_out_desc= (
			'JSON dictionary containing list of detected sources, islands and fitted components along with their measured parameters'
		)
		
		json_catalog_out_format= (
			'JSON dictionary follows the format below: \n\n'
			'{\n'
			'  "metadata": {...}\n'
			'  "sources": [\n'
			'     {\n'
			'       "name": "S0",\n'
			'       ...\n'
			'       "islands": [\n'
			'         {\n'
			'           "name": "S0",\n'
			'           "Stot": 0.01,\n'
			'           "fit_info": {\n'
			'              "ncomponents": 1,\n'
			'              "components": [\n'
			'                 {\n'
			'                    "S": 0.002,\n'
			'                    "S_err": 0.0001,\n'
			'                    ...\n'
			'                 },\n'
			'                 ...\n'
			'              ]\n'
			'           }\n'
			'           ...\n'
			'         }\n'
			'       ]\n'
			'     },\n'
			'     ...\n'
			'  ]\n'
			'}\n'
			'where:\n'
			'* metadata | dict: Placeholder for info on the input image data parameters (taken from the FITS header), software version/tags. Not filled\n'
			'* sources | List(dict) : list length equal to the number of extracted sources, with each dictionary containing parameters for each detected source, listed below: \n'
			'    - name | str: Source name, usually with an "S" prefix followed by an integer\n'
			'    - x_wcs/y_wcs | float: Source centroid position in sky WCS coordinates (unit: deg). Coordinate system reported in "cs" field\n'
			'    - x_wcs_str/y_wcs_str | str: Island centroid sky WCS coordinate position in sexigecimal format. Coordinate system reported in "cs" field\n'
			'    - cs | str: Sky coordinate system {"fk5","galactic"}. "fk5" is J2000 RightAscension/Declination\n'
			'    - nest_level | int: Source depth level {0: parent source, 1: nested source, 2: nested of nested source, etc...}\n'
			'    - nislands | int: Number of source islands found inside this source\n'
			'    - islands | List(dict): list length equal to the number of source islands, with each dictionary containing parameters for each detected island, detailed below \n'
			'\n'
			'    *islands: A group of 4-connected pixels with intensity above a detection threshold with respect to the sky background level. A source may contain one or more islands and an island may contain one or multiple source components. Caesar usually produces 1 island per source, unless nested source search is activated.\n'
			'        - name | str: Island name, usually with an "S" prefix followed by an integer\n'
			'        - iau_name | str: Island name in IAU notation\n'
			'        - uuid | str: Universally unique identifier for this island'
			'        - npix | int: Number of image pixels belonging to the island\n'
			'        - x_wcs/y_wcs | float: Island centroid position in sky WCS coordinates (unit: deg). Coordinate system reported in "cs" field\n'
			'        - cs | str: Sky coordinate system {"fk5","galactic"}. "fk5" is J2000 RightAscension/Declination\n'
			'        - x_width/y_width | float: Island extent along x- and y-axis direction in image pixel coordinates\n'
			'        - max_angular_size | float: Largest distance between to points on the boundary of the island (unit: deg)\n'
			'        - pa | float: Position angle of the max_angular_size line (unit: deg)\n'
			'        - beam_area | float: Area of the synthesized beam (psf) (unit: deg^2)\n'
			'        - Smax | float: Max pixel brightness in island (unit: Jy/beam)\n'
			'        - Stot | float: Sum of island pixel brightness divided by beam area (unit: Jy)\n'
			'        - eta | float: Correction factor for Sint that is meant to account for the flux that was not included because it was below the clipping limit. For a point source the true flux should be Sint/eta. For extended sources this is not always the case so use with caution.\n'
			'        - bkg | float: Background flux density (unit: Jy/beam)\n'
			'        - rms | float: Local noise rms (unit: Jy/beam)\n'
			'        - fit_flags | str: Fitting flags. Should be all 0 for a good fit, otherwise set to: \n'
			'            1 (FITERRSMAL): islands are not able to be fit due to there being fewer pixels than free parameters\n'
			'            2 (FITERR): an error occurs during the fitting process. eg the fit does not converge\n'
			'            4 (FIXED2PSF): a component is forced to have the shape of the local point spread function then this flag is set. This flag is often set at the same time as the FITERRSMALL, or FIXEDCRICULAR\n'
			'            8 (FIXEDCRICULAR): a source is forced to have a circular shape then this flag will be fit\n'
			'            16 (NOTFIT): a component is not fit then this flag is set. This can because and island has reached the --maxsummits limit, or --measure mode has been invoked\n'
			'            32 (WCSERR): conversion from pixel to sky coordinates does not work then this flag will be set. This can happen for strange projections, but more likely when an image contains pixles that do not have valid sky coordinates\n'
			'            64 (PRIORIZED): when the source was fit using prorized fitting\n'
			'        - fit_info | dict: Island fitting information, described below. Empty when --fitsources is disabled or when no fit info was found (e.g. failed fitting)\n'
			'\n'
			'        *fit_info: Dictionary containing island fitting parameters when computed/found, described below:\n'
			'            - ncomponents | int: Number of 2D fit components found\n'
			'            - model | str: Fit component model {"gaus"}\n'
			'            - ndata | int: Number of island pixels used in fitting\n'
			'            - components | List(dict): Collection of fit component parameters, described below\n'
			'\n'
			'            *components: List of dictionaries, each containing individual component fit info, described below:\n'
			'                - iau_name | str: Component name in IAU notation\n'
			'                - uuid | str: Universally unique identifier for this component\n'
			'                - x_wcs/y_wcs | float: Component centroid position in sky WCS coordinates (unit: deg). Coordinate system reported in "cs" field \n'
			'                - x_wcs_err/y_wcs_err | float: Error on component centroid position in sky WCS coordinates (unit: deg)\n'
			'                - cs | str: Sky coordinate system {"fk5","galactic"}. "fk5" is J2000 RightAscension/Declination\n'
			'                - Speak/Speak_err | float: Component peak flux parameter and its error (unit: Jy/beam)\n'
			'                - S/S_err | float: Component integrated flux density (already divided by beam area) and its error (unit: Jy)\n'
			'                - bkg | float: Background flux density (unit: Jy/beam)\n'
			'                - rms | float: Local noise rms (unit: Jy/beam)\n'
			'                - bmaj/bmin/pa | float: Component fit ellipse major/minor axis (unit: arcsec) and position angle (unit: deg, measured counterclock-wise from North)\n'
			'                - bmaj_err/bmin_err/pa_err | float: Errors on fit ellipse major/minor axis (unit: arcsec) and position angle (unit: deg) \n'
			'                - fit_flags | str: Fitting flags. Should be all 0 for a good fit, otherwise set to: \n'
			'                    1 (FITERRSMAL): islands are not able to be fit due to there being fewer pixels than free parameters\n'
			'                    2 (FITERR): an error occurs during the fitting process. eg the fit does not converge\n'
			'                    4 (FIXED2PSF): a component is forced to have the shape of the local point spread function then this flag is set. This flag is often set at the same time as the FITERRSMALL, or FIXEDCRICULAR\n'
			'                    8 (FIXEDCRICULAR): a source is forced to have a circular shape then this flag will be fit\n'
			'                    16 (NOTFIT): a component is not fit then this flag is set. This can because and island has reached the --maxsummits limit, or --measure mode has been invoked\n'
			'                    32 (WCSERR): conversion from pixel to sky coordinates does not work then this flag will be set. This can happen for strange projections, but more likely when an image contains pixles that do not have valid sky coordinates\n'
			'                    64 (PRIORIZED): when the source was fit using prorized fitting\n'
			'                - residual_mean | float: Mean of the residual flux remaining in the island after fitted Gaussian is subtracted\n'
			'                - residual_std | float: Standard deviation of the residual flux remaining in the island after fitted Gaussian is subtracted\n'
			'                - psf_a/psf_b/psf_pa | float: the semi-major/semi-minor axis and position angle of the point spread function at this location (unit: arcsec)\n'
		)
		
		ascii_catalog_out_desc= (
			'Ascii tabular data file containing extracted source islands (rows), and their measured parameters (columns)'
		)
			
		ascii_catalog_out_format= (
			'Ascii tabular data file follows this format: each row is a source island, while columns represent island parameters, described below:\n'
			'- Col 1: island | int: Numerical indication of the island\n'
			'- Col 2: components | int: Number of fitted components within this island\n'
			'- Col 3: bkg | float: Background flux density (unit: Jy/beam)\n'
			'- Col 4: rms | float: Local noise rms (unit: Jy/beam)\n'
			'- Col 5-6: ra_str/dec_str (lon_str/lat_str) | str: Island centroid J2000 Right-Ascension/Declination (or Galactic longitude l/latitude b) position in sexigecimal format\n'
			'- Col 7-8: ra/dec (lon/lat) | float: Island centroid J2000 Right-Ascension/Declination (or Galactic longitude l/latitude b) position (unit: deg)\n'
			'- Col 9: Speak | float: Peak flux density of the brightest pixel in the island (unit: Jy/beam)\n'
			'- Col 10: Sint | float: Island integrated flux density (computed by summing pixels in the island, and dividing by the synthesized beam size) (unit: Jy)\n'
			'- Col 11: Sint_err | float: Error on island integrated flux density. Currently set to nan as not computed (unit: Jy)\n'
			'- Col 12: eta | float: Correction factor for Sint that is meant to account for the flux that was not included because it was below the clipping limit. For a point source the true flux should be Sint/eta. For extended sources this is not always the case so use with caution.\n'
			'- Col 13-14: x_width/y_width | float: Island extent along x- and y-axis direction in image pixel coordinates\n'
			'- Col 15: max_angular_size | float: Largest distance between to points on the boundary of the island (unit: deg)\n'
			'- Col 16: pa | float: Position angle of the max_angular_size line (unit: deg)\n'
			'- Col 17: npix | int: Number of pixels within the island\n'
			'- Col 18: beam_area | float: Area of the synthesized beam (psf) (unit: deg^2)\n'
			'- Col 19: fit_flags | str: Fitting flags. Should be all 0 for a good fit, otherwise set to: \n'
			'     1 (FITERRSMAL): islands are not able to be fit due to there being fewer pixels than free parameters\n'
			'     2 (FITERR): an error occurs during the fitting process. eg the fit does not converge\n'
			'     4 (FIXED2PSF): a component is forced to have the shape of the local point spread function then this flag is set. This flag is often set at the same time as the FITERRSMALL, or FIXEDCRICULAR\n'
			'     8 (FIXEDCRICULAR): a source is forced to have a circular shape then this flag will be fit\n'
			'     16 (NOTFIT): a component is not fit then this flag is set. This can because and island has reached the --maxsummits limit, or --measure mode has been invoked\n'
			'     32 (WCSERR): conversion from pixel to sky coordinates does not work then this flag will be set. This can happen for strange projections, but more likely when an image contains pixles that do not have valid sky coordinates\n'
			'     64 (PRIORIZED): when the source was fit using prorized fitting\n'
			'- Col 20: uuid | str: Universally unique identifier for this island'
		)
		
		
		ascii_fitcomp_catalog_out_desc= (
			'Ascii tabular data file containing fitted components (rows) found in extracted source islands, , and their measured parameters (columns)'
		)
		
		ascii_fitcomp_catalog_out_format= (
			'Ascii tabular data file follows this format: each row is a fitted component, while columns represent component parameters, described below:\n'
			'- Col 1: island | int: Numerical indication of the island from which the source was fitted\n'
			'- Col 2: source | int: Source number within that island\n'
			'- Col 3: bkg | float: Background flux density (unit: Jy/beam)\n'
			'- Col 4: rms | float: Local noise rms (unit: Jy/beam)\n'
			'- Col 5-6: ra_str/dec_str (lon_str/lat_str) | str: Component centroid J2000 Right-Ascension/Declination (or Galactic longitude l/latitude b) position in sexigecimal format\n'
			'- Col 7-8: ra/ra_err (lon/lon_err)| float: Component centroid J2000 Right-Ascension (or Galactic longitude l) position and its error (unit: deg)\n'
			'- Col 9-10: dec/dec_err (lat/lat_err) | float: Component centroid J2000 Declination (or Galactic latitude b) position and its error (unit: deg)\n'
			'- Col 11-12: Speak/Speak_err | float: Component peak flux density and its error (unit: Jy/beam)\n'
			'- Col 13-14: Sint/Sint_err | float: Component integrated flux density, computed from a/b/Speak and the synthesized beam size, and its error (unit: Jy)\n'
			'- Col 15-16: a/a_err | float: Component ellipse semi-major axis and its error (unit: arcsec)\n'
			'- Col 17-18: b/b_err | float Component ellipse semi-minor axis and its error (unit: arcsec)\n'
			'- Col 19-20: pa/pa_err | float: Component ellipse position angle and its error (unit: deg)\n'
			'- Col 21: fit_flags | str: Fitting flags. Should be all 0 for a good fit, otherwise set to: \n'
			'     1 (FITERRSMAL): islands are not able to be fit due to there being fewer pixels than free parameters\n'
			'     2 (FITERR): an error occurs during the fitting process. eg the fit does not converge\n'
			'     4 (FIXED2PSF): a component is forced to have the shape of the local point spread function then this flag is set. This flag is often set at the same time as the FITERRSMALL, or FIXEDCRICULAR\n'
			'     8 (FIXEDCRICULAR): a source is forced to have a circular shape then this flag will be fit\n'
			'     16 (NOTFIT): a component is not fit then this flag is set. This can because and island has reached the --maxsummits limit, or --measure mode has been invoked\n'
			'     32 (WCSERR): conversion from pixel to sky coordinates does not work then this flag will be set. This can happen for strange projections, but more likely when an image contains pixles that do not have valid sky coordinates\n'
			'     64 (PRIORIZED): when the source was fit using prorized fitting\n'
			'- Col 22: residual_mean | float: Mean of the residual flux remaining in the island after fitted Gaussian is subtracted\n'
			'- Col 23: residual_std | float: Standard deviation of the residual flux remaining in the island after fitted Gaussian is subtracted\n'
			'- Col 24: uuid | str: Universally unique identifier for this component\n'
			'- Col 25-27: psf_a/psf_b/psf_pa | float: the semi-major/semi-minor axis and position angle of the point spread function at this location (unit: arcsec)\n'
		)
		
		
		self.job_outputs= {
			"catalog_json": {
				"path": None,
				"glob": "catalog-*.json",
				"type": "application/json",
				"role": "primary_result",
				"description": json_catalog_out_desc,
				"format": json_catalog_out_format,
				"parser": "json",
				"required": True,
				"notes": (
					""
				)
			},
			"catalog_ascii": {
				"path": None,
				"glob": "catalog-*_isle.tab",
				"type": "text/plain",
				"role": "catalog",
				"description": ascii_catalog_out_desc,
				"format": ascii_catalog_out_format,
				"parser": "text",
				"required": False,
				"notes": (
					""
				)
			},
			"catalog_components_ascii": {
				"path": None,
				"glob": "catalog-*_comp.tab",
				"type": "text/plain",
				"role": "catalog",
				"description": ascii_fitcomp_catalog_out_desc,
				"format": ascii_fitcomp_catalog_out_format,
				"parser": "text",
				"required": False,
				"notes": (
					""
				)
			},
			"plot": {
				"path": None,
				"glob": "plot_*.png",
				"type": "image/png",
				"role": "visualization",
				"description": "Image with detections overlaid.",
				"format": "",
				"parser": "image",
				"required": False,
				"notes": (
					""
				)
			},
			"region": {
				"path": None,
				"glob": "ds9-*_isle.reg",
				"type": "application/x-ds9",
				"role": "visualization",
				"description": "A DS9 region file containing detected source island contour as line regions.",
				"format": "",
				"parser": "ds9",
				"required": False,
				"notes": (
					""
				)
			},
			"region_components": {
				"path": None,
				"glob": "ds9-*_comp.reg",
				"type": "application/x-ds9",
				"role": "visualization",
				"description": "A DS9 region file containing fitted components inside detected source island as ellipse regions.",
				"format": "",
				"parser": "ds9",
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
		self.cmd_args.append("--save-summaryplot")
		self.cmd_args.append("--save-regions ")
		self.cmd_args.append("--save-catalog-to-json ")


	
	def set_data_input_option_value(self):
		""" Set app input option value """

		input_opt= "".join("--inputfile=%s" % self.data_inputs)
		self.cmd_args.append(input_opt)


	def transform_inputfile(self, file_uuid):
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
			logger.warn("inputfile uuid %s is empty or not found in the system!" % file_uuid, action="submitjob")
			return ''

		logger.info("inputfile uuid %s converted in %s ..." % (file_uuid,file_path), action="submitjob")

		return file_path
		
