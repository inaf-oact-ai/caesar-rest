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
#   FEAT EXTRACTOR APP CONFIGURATOR
##########################################
MODEL_CONTAINER_VARIANTS = {
	"simclr_radio": "tf",
	"dinov2": "torch",
	"dinov3": "torch",
	"dinov2_legacy": "torch",
	"siglip": "torch",
	"siglip2": "torch",
	"chronos2": "chronos",
	"moirai2": "moirai",
	"falcon1": "falcon",
	"fats": "fats",
	"licu": "licu",	
	"astromer1": "licu",
	"astromer1-ztfdr20": "licu",
	"astromer2": "licu",
	"moment1-small": "licu",
	"moment1-base": "licu",
	"moment1-large": "licu",
	"astra-clr": "licu",
	"atat": "licu",
	"atcat": "licu",
}

IMAGE_MODELS = {
	"simclr_radio",
	"dinov2",
	"dinov3",
	"dinov2_legacy",
	"siglip",
	"siglip2",
}

LICU_SINGLE_CHANNEL_EMBED_MODELS = {
	"astromer1",
	"astromer1-ztfdr20",
	"astromer2",
	"moment1-small",
	"moment1-base",
	"moment1-large",
}

LICU_MULTIBAND_EMBED_MODELS = {
	"astra-clr",
	"atat",
	"atcat",
}

LICU_EMBED_MODELS = (
	LICU_SINGLE_CHANNEL_EMBED_MODELS
	| LICU_MULTIBAND_EMBED_MODELS
)

TIMESERIES_MODELS = {
	"chronos2",
	"moirai2",
	"falcon1",
	"licu",
	"fats",
} | LICU_EMBED_MODELS

IMAGE_ONLY_OPTIONS = {
	"norm-min",
	"norm-max",
	"imgsize",
	"nchannels",
	"clipdata",
	"zscale",
	"zscale-contrast",
	"set-zero-to-min",
	"reset-meanstd",
	"reset-rescale",
}

TIMESERIES_ONLY_OPTIONS = {
	"timeseries-layout",
	"time-column",
	"value-columns",
	"error-columns",
	"band-column",
	"value-prefixes",
	"error-prefixes",
	"time-prefix",
	"time-start-column",
	"cadence-column",
	"channel-names",
	"label-column",
	"metadata-columns",
	"time-start-key",
	"cadence-key",
	"band-key",
	"regularize",
	"cadence",
	"missing-strategy",
	"aggregation",
	"context-length",
	"batch-size",
	"patching-mode",
	"token-order",
	"regularization-method",
	"bin-aggregation",
	"gp-sigma",
	"gp-rho",
	"gp-jitter",
	"timeseries-plot",
	"feature-set",
	"invalid-feature-policy",
	"min-samples",
	"licu-embed-output",
	"licu-embed-reduction",
	"licu-mag-zp",
	"licu-allow-extra-bands",
	"input-sample-policy",
}

# - Common representation options not supported by Moirai-2
MOIRAI_UNSUPPORTED_COMMON_OPTIONS = {
	"context-length",
	"batch-size",
}

MOIRAI_ONLY_OPTIONS = {
	"patching-mode",
	"token-order",
}

LICU_HANDCRAFTED_ONLY_OPTIONS = {
	"feature-set",
	"invalid-feature-policy",
}

LICU_EMBED_ONLY_OPTIONS = {
	"licu-embed-output",
	"licu-embed-reduction",
}

LICU_MULTIBAND_ONLY_OPTIONS = {
	"band-column",
	"band-key",
	"licu-mag-zp",
	"licu-allow-extra-bands",
}

LICU_COMMON_OPTIONS = {
	"min-samples",
}

LICU_ALL_OPTIONS = (
	LICU_HANDCRAFTED_ONLY_OPTIONS
	| LICU_EMBED_ONLY_OPTIONS
	| LICU_MULTIBAND_ONLY_OPTIONS
	| LICU_COMMON_OPTIONS
)

FALCON_UNSUPPORTED_OPTIONS = {
	"batch-size",
} | MOIRAI_ONLY_OPTIONS | LICU_ALL_OPTIONS

LICU_HANDCRAFTED_UNSUPPORTED_OPTIONS = {
	"aggregation",
	"context-length",
	"batch-size",
	"patching-mode",
	"token-order",
}

LICU_EMBED_UNSUPPORTED_OPTIONS = {
	"feature-set",
	"invalid-feature-policy",
	"context-length",
	"batch-size",
	"patching-mode",
	"token-order",
}

LICU_MODEL_OUTPUTS = {
	"astromer1": {
		"mean",
		"max",
		"sequence",
	},
	"astromer1-ztfdr20": {
		"mean",
		"max",
		"sequence",
	},
	"astromer2": {
		"mean",
		"max",
		"sequence",
	},
	"moment1-small": {
		"mean",
		"sequence",
	},
	"moment1-base": {
		"mean",
		"sequence",
	},
	"moment1-large": {
		"mean",
		"sequence",
	},
	"astra-clr": {
		"mean",
	},
	"atat": {
		"token",
		"mean",
		"sequence",
	},
	"atcat": {
		"last",
		"mean",
		"sequence",
	},
}

class FeatExtractorAppConfigurator(AppConfigurator):
	""" Class to configure feature extractor application """

	def __init__(self, app_name="fextractor"):
		""" Return app configurator class """
		AppConfigurator.__init__(self, app_name=app_name)

		# - Define cmd name
		self.cmd= 'run_fextractor.sh'
		self.cmd_args= []
		self.batch_processing_support= True
		
		# - Describe app
		self.description = (
			"Extract fixed-size data representations (features/embeddings) from scientific data using pretrained foundation models or statistical feature extractors. "
			"Currently supported input modalities are:\n"
			"* images\n"
			"* time series\n\n"
			"Time-series inputs can be supplied as CSV tables or JSON datalists. Both regularly and irregularly sampled time series are supported, depending on the selected backend. "
			"Time-series data may contain one or multiple value channels and optional measurement uncertainties."
		)
		
		
		
		self.tool_categories = [
			"image",
			"timeseries",
		]
		
		
		input_timeseries_long_format = (
			'Input long-format time-series CSV file has this format:\n'
			'- One observation/sample per row\n'
			'- time | float: Timestamp column, specified with the time-column option\n'
			'- var1,var2,... | float: One or more time-series value columns, specified with value-columns\n'
			'- var1_err,var2_err,... | float: Optional measurement uncertainty/error columns, specified with error-columns\n'
			'Regularly and irregularly sampled time series are supported. '
			'For irregular sampling, explicit timestamps must be provided.'
		)

		input_timeseries_wide_format = (
			'Input wide-format time-series CSV file has this format:\n'
			'- One time series per row/file\n'
			'- var1_0,var1_1,...,var1_N | float: Samples for the first value channel\n'
			'- var2_0,var2_1,...,var2_N | float: Samples for additional value channels\n'
			'- var1_err_0,var1_err_1,... | float: Optional uncertainty samples\n'
			'- time_0,time_1,...,time_N | float: Optional explicit timestamps for irregular sampling\n'
			'- t_start | float and dt | float: Optional initial timestamp and cadence for regular sampling\n'
			'Value column prefixes are specified with value-prefixes. '
			'Optional uncertainty prefixes are specified with error-prefixes. '
			'Irregular timestamp prefixes are specified with time-prefix. '
			'For regularly sampled wide data, time-start-column and cadence-column may be used.'
		)

		input_timeseries_json_file_format = (
			'Input JSON datalist with file-based time-series entries has this format:\n\n'
			'{\n'
			'  "data": [\n'
			'    {\n'
			'      "label": "X",\n'
			'      "filepath": "/path/to/timeseries.csv"\n'
			'    },\n'
			'    ...\n'
			'  ]\n'
			'}\n'
			'\n'
			'where:\n'
			'* filepath | str: Path to the input time-series CSV file\n'
			'* label | str or list(str): Optional class label(s)\n'
			'Additional metadata fields specified in each entry are preserved in the output JSON. '
			'The datalist dictionary key is configured with datalist-key (default=data).'
		)

		input_timeseries_json_irregular_format = (
			'Input JSON datalist with inline irregularly sampled time series has this format:\n\n'
			'{\n'
			'  "data": [\n'
			'    {\n'
			'      "t": [0.0, 0.7, 2.1, ...],\n'
			'      "var1": [1.0, 1.1, 0.9, ...],\n'
			'      "var2": [4.0, 4.5, 5.0, ...],\n'
			'      "var1_err": [0.1, 0.1, 0.2, ...],\n'
			'      "var2_err": [0.3, 0.2, 0.3, ...]\n'
			'    },\n'
			'    ...\n'
			'  ]\n'
			'}\n'
			'\n'
			'where:\n'
			'* t | list(float): Explicit observation timestamps, selected with time-column\n'
			'* var1,var2,... | list(float): Time-series value arrays, selected with value-columns\n'
			'* var1_err,var2_err,... | list(float): Optional uncertainty arrays, selected with error-columns\n'
			'Additional metadata fields specified in each entry are preserved in the output JSON.'
		)

		input_timeseries_json_regular_format = (
			'Input JSON datalist with inline regularly sampled time series has this format:\n\n'
			'{\n'
			'  "data": [\n'
			'    {\n'
			'      "t_start": 0.0,\n'
			'      "dt": 1.0,\n'
			'      "var1": [1.0, 1.1, 0.9, ...],\n'
			'      "var2": [4.0, 4.5, 5.0, ...],\n'
			'      "var1_err": [0.1, 0.1, 0.2, ...],\n'
			'      "var2_err": [0.3, 0.2, 0.3, ...]\n'
			'    },\n'
			'    ...\n'
			'  ]\n'
			'}\n'
			'\n'
			'where:\n'
			'* t_start | float: Initial timestamp, selected with time-start-key\n'
			'* dt | float: Sampling cadence, selected with cadence-key\n'
			'* var1,var2,... | list(float): Time-series value arrays, selected with value-columns\n'
			'* var1_err,var2_err,... | list(float): Optional uncertainty arrays, selected with error-columns\n'
			'Additional metadata fields specified in each entry are preserved in the output JSON.'
		)

		input_data_expected = (
			'Astronomical/scientific image or time-series input.\n\n'
			+ input_timeseries_long_format
			+ '\n\n'
			+ input_timeseries_wide_format
			+ '\n\n'
			+ input_timeseries_json_file_format
			+ '\n\n'
			+ input_timeseries_json_irregular_format
			+ '\n\n'
			+ input_timeseries_json_regular_format
		)

		self.input_requirements = {
			"supported_formats": [
				"fits",
				"png",
				"jpg",
				"jpeg",
				"csv",
				"ecsv",
				"npy",
				"npz",
				"json",
			],
			"expected_data": input_data_expected,
			"notes": [
				"Chronos-2, Moirai-2, and Falcon-1 support uni- and multivariate time series.",
				"Falcon-1 processes multiple value channels independently according to the "
				"upstream model semantics and aggregates their contextual representations.",
				"LiCu handcrafted feature extraction processes each value channel "
				"independently and concatenates the resulting feature vectors.",
				"LiCu ML single-channel embedding models include Astromer 1, Astromer 1 "
				"ZTF DR20, Astromer 2, and MOMENT-1 small/base/large. Each input "
				"value channel is embedded independently and the resulting vectors "
				"are concatenated.",
				"LiCu native multiband embedding models include AstraCLR, ATAT, and "
				"ATCAT. They consume one value stream together with timestamps and "
				"a photometric-band label for each observation.",
				"Astromer models use timestamps and naturally support irregularly "
				"sampled time series. MOMENT-1 consumes the ordered value sequence.",
				"Measurement uncertainties are optional for the common time-series "
				"input representation. LiCu single-channel embedders do not consume "
				"measurement uncertainties directly; AstraCLR and ATCAT require one "
				"uncertainty field, while ATAT accepts it optionally.",
				"FATS processes each value channel independently and concatenates "
				"the resulting feature vectors; cross-channel relationships are "
				"not modeled.",
				"Measurement uncertainties are optional. LiCu handcrafted feature "
				"extraction and FATS can use one uncertainty series per value channel.",
				"Available input and preprocessing options depend on the selected backend.",
			],
		}
		
		self.limitations = [
			"Available preprocessing options depend on the selected model modality.",

			"Chronos-2 and Falcon-1 require regularly sampled time series unless "
			"regularization is enabled.",
			
			"Falcon-1 processes multiple time-series value channels independently; "
			"cross-channel relationships are not modeled.",
			"Falcon-1 supports aggregation and context-length options, but does not "
			"support batch-size or Moirai-specific patching options.",

			"LiCu handcrafted and single-channel ML embedding models process each "
			"time-series value channel independently; cross-channel relationships "
			"are not modeled. AstraCLR, ATAT, and ATCAT instead use native "
			"multiband observations.",

			"LiCu handcrafted feature extraction does not use learned-representation "
			"aggregation, context-length, batch-size, or Moirai-specific patching "
			"options.",

			"LiCu ML embedding models support model-native output/reduction options. "
			"Sequence embeddings can additionally use the common aggregation option. "
			"Context-length, batch-size, and Moirai-specific patching options are "
			"not supported.",
			
			"FATS processes each time-series value channel independently; "
			"cross-variable relationships are not modeled.",

			"FATS does not support learned-representation aggregation, "
			"context-length, batch-size, regularization, or "
			"Moirai-specific patching options.",
			
			"FATS uses its legacy native preprocessing path and does not "
			"support the common fextractor time-series regularization, "
			"interpolation, or Gaussian-Process preprocessing options.",
		]
		
		# - Define dictionary with allowed options
		self.valid_options= {
		
			
			# == MODEL OPTIONS ==
			'model' : EnumValueOption(
				name='model',
				value='',
				value_type=str,
				description='Feature extraction model to be used',
				category='MODEL',
				default_value='simclr_radio',
				allowed_values=[
					'simclr_radio',
					'dinov2',
					'dinov3',
					'dinov2_legacy',
					'siglip',
					'siglip2',
					'chronos2',
					'moirai2',
					'falcon1',
					'fats',
					'licu',
					'astromer1',
					'astromer1-ztfdr20',
					'astromer2',
					'moment1-small',
					'moment1-base',
					'moment1-large',
					'astra-clr',
					'atat',
					'atcat',
				]
			),

			# == INPUT OPTIONS ==
			'datalist-key' : ValueOption(
				name='datalist-key',
				value='',
				value_type=str,
				description='Dictionary key containing datalist entries',
				category='INPUT',
				default_value='data'
			),

			'nmax' : ValueOption(
				name='nmax',
				value='',
				value_type=int,
				description='Maximum number of datalist entries to process',
				category='INPUT',
				default_value='',
				min_value=1
			),
		
			# == IMAGE PRE-PROCESSING OPTIONS ==
			"preproc-profile": EnumValueOption(
				name="preproc-profile",
				value="",
				value_type=str,
				description=(
					"Domain preprocessing profile. "
					"'simclr_radio' applies to image models; "
					"'default' is available for both image and time-series models."
				),
				category="PREPROCESSING",
				#default_value="",
				default_value="default",
				allowed_values=["default", "simclr_radio"]
			),
			'norm-min' : ValueOption(
				name='norm-min',
				value='',
				value_type=float, 
				description='Normalization min value (default=0)',
				category='PREPROCESSING',
				default_value=0.0,
				min_value=-1.0,
				max_value=0.0
			),
			'norm-max' : ValueOption(
				name='norm-max',
				value='',
				value_type=float, 
				description='Normalization max value (default=1)',
				category='PREPROCESSING',
				default_value=1.0,
				min_value=1.0,
				max_value=255.0
			),
			'imgsize' : ValueOption(
				name='imgsize',
				value='',
				value_type=int,
				description=(
					'Model input image size in pixels. '
					'If omitted, the selected model default is used.'
				),
				category='PREPROCESSING',
				default_value='',
				min_value=16,
				max_value=1024
			),
			'nchannels' : ValueOption(
				name='nchannels',
				value='',
				value_type=int,
				description=(
					'Number of model input channels. '
					'If omitted, the selected model default is used.'
				),
				category='PREPROCESSING',
				default_value='',
				min_value=1,
				max_value=1000
			),
			'clipdata' : Option(
				name='clipdata', 
				description='Clip image pixel value in range [mean-5*stddev, mean+30*stddev]', 
				category='PREPROCESSING',
				default_value=False
			),
			'zscale' : Option(
				name='zscale',
				description=(
					'Enable or disable z-scale stretching. '
					'If omitted, the preprocessing profile default is used.'
				),
				category='PREPROCESSING',
				default_value=None
			),
			'zscale-contrast' : ValueOption(
				name='zscale-contrast',
				value='',
				value_type=float, 
				description='zscale contrast value applied to all channels',
				category='PREPROCESSING',
				default_value=0.25,
				min_value=0.0,
				max_value=1.0,
			),
			'set-zero-to-min' : Option(
				name='set-zero-to-min',
				description=(
					'Replace zero/blank/non-finite pixels with the minimum '
					'valid non-zero image value.'
				),
				category='PREPROCESSING',
				default_value=False
			),
			'reset-meanstd' : Option(
				name='reset-meanstd',
				description='Reset SigLIP/SigLIP2 processor mean/std to 0/1',
				category='PREPROCESSING',
				default_value=False
			),
			'reset-rescale' : Option(
				name='reset-rescale',
				description='Disable SigLIP/SigLIP2 processor input rescaling',
				category='PREPROCESSING',
				default_value=False
			),
			
			# == TIME-SERIES PREPROCESSING OPTIONS ==
			'timeseries-layout' : EnumValueOption(
				name='timeseries-layout',
				value='',
				value_type=str,
				description='Time-series tabular layout',
				category='TIMESERIES',
				default_value='',
				allowed_values=['long', 'wide']
			),
			
			'time-column' : ValueOption(
				name='time-column',
				value='',
				value_type=str,
				description=(
					'Timestamp column for long-format CSV input, or field '
					'name containing the timestamp array for inline JSON input'
				),
				category='TIMESERIES',
				default_value=''
			),

			'value-columns' : ValueOption(
				name='value-columns',
				value='',
				value_type=str,
				description=(
					'Colon-separated time-series value columns. '
					'The container wrapper converts them to CLI arguments.'
				),
				category='TIMESERIES',
				default_value=''
			),

			'error-columns' : ValueOption(
				name='error-columns',
				value='',
				value_type=str,
				description=(
					'Colon-separated measurement uncertainty/error columns '
					'or inline JSON uncertainty-array fields. '
					'For FATS, one error field must be supplied per value field.'
				),
				category='TIMESERIES',
				default_value=''
			),

			'band-column' : ValueOption(
				name='band-column',
				value='',
				value_type=str,
				description=(
					'Long-layout column containing one photometric band '
					'label per observation. Used by LiCu multiband ML '
					'embedding models.'
				),
				category='TIMESERIES',
				default_value=''
			),

			'value-prefixes' : ValueOption(
				name='value-prefixes',
				value='',
				value_type=str,
				description='Colon-separated value prefixes for wide-layout input',
				category='TIMESERIES',
				default_value=''
			),

			'error-prefixes' : ValueOption(
				name='error-prefixes',
				value='',
				value_type=str,
				description=(
					'Colon-separated uncertainty/error prefixes for '
					'wide-layout time-series input. One error prefix '
					'must be supplied per value prefix.'
				),
				category='TIMESERIES',
				default_value=''
			),

			'time-prefix' : ValueOption(
				name='time-prefix',
				value='',
				value_type=str,
				description=(
					'Prefix of indexed timestamp columns for irregularly '
					'sampled wide-layout time-series input'
				),
				category='TIMESERIES',
				default_value=''
			),

			'time-start-column' : ValueOption(
				name='time-start-column',
				value='',
				value_type=str,
				description=(
					'Column containing the initial timestamp for regularly '
					'sampled wide-layout time-series input'
				),
				category='TIMESERIES',
				default_value=''
			),

			'cadence-column' : ValueOption(
				name='cadence-column',
				value='',
				value_type=str,
				description=(
					'Column containing the sampling cadence for regularly '
					'sampled wide-layout time-series input'
				),
				category='TIMESERIES',
				default_value=''
			),

			'channel-names' : ValueOption(
				name='channel-names',
				value='',
				value_type=str,
				description=(
					'Colon-separated names assigned to time-series channels. '
					'For FATS these names prefix the per-channel feature names.'
				),
				category='TIMESERIES',
				default_value=''
			),

			'label-column' : ValueOption(
				name='label-column',
				value='',
				value_type=str,
				description='Optional sample-level label column',
				category='TIMESERIES',
				default_value=''
			),

			'metadata-columns' : ValueOption(
				name='metadata-columns',
				value='',
				value_type=str,
				description='Colon-separated additional sample-level metadata columns',
				category='TIMESERIES',
				default_value=''
			),

			'time-start-key' : ValueOption(
				name='time-start-key',
				value='',
				value_type=str,
				description='Inline JSON field containing the initial timestamp',
				category='TIMESERIES',
				default_value=''
			),

			'cadence-key' : ValueOption(
				name='cadence-key',
				value='',
				value_type=str,
				description='Inline JSON field containing the sampling cadence',
				category='TIMESERIES',
				default_value=''
			),

			'band-key' : ValueOption(
				name='band-key',
				value='',
				value_type=str,
				description=(
					'Inline JSON field containing one photometric band '
					'label per observation. Used by LiCu multiband ML '
					'embedding models.'
				),
				category='TIMESERIES',
				default_value=''
			),

			'regularize' : Option(
				name='regularize',
				description=(
					'Enable or disable projection of the input time series '
					'onto a regular temporal grid. The selected '
					'regularization-method controls how grid values are '
					'constructed.'
				),
				category='TIMESERIES',
				default_value=False
			),

			'cadence' : ValueOption(
				name='cadence',
				value='',
				value_type=float,
				description=(
					'Target regularization cadence in the same units as '
					'the input timestamps. GP regularization currently '
					'requires an explicit cadence.'
				),
				category='TIMESERIES',
				default_value='',
				min_value=0.0
			),
			
			'missing-strategy' : EnumValueOption(
				name='missing-strategy',
				value='',
				value_type=str,
				description=(
					'Missing-bin strategy used with bin regularization. '
					"'nan' leaves gaps unchanged; 'linear' performs linear "
					"interpolation; 'pchip' uses shape-preserving cubic "
					"interpolation; 'akima' uses Akima interpolation; "
					"'cubic' uses a cubic spline. Interpolation is limited "
					"to internal gaps and does not extrapolate outside the "
					"observed range."
				),
				category='TIMESERIES',
				default_value='',
				allowed_values=[
					'nan',
					'linear',
					'pchip',
					'akima',
					'cubic',
				]
			),
			
			'regularization-method' : EnumValueOption(
				name='regularization-method',
				value='',
				value_type=str,
				description=(
					'Regularization method used to project a time series '
					'onto a regular grid. '
					"'bin' assigns observations to cadence bins and optionally "
					'interpolates missing bins; '
					"'gp' fits a Gaussian Process directly to the observed "
					'timestamps and predicts the regularized series on the '
					'target grid.'
				),
				category='TIMESERIES',
				default_value='',
				allowed_values=[
					'bin',
					'gp',
				]
			),

			'bin-aggregation' : EnumValueOption(
				name='bin-aggregation',
				value='',
				value_type=str,
				description=(
					'Aggregation applied when multiple observations fall '
					'into the same regularization bin. '
					"'mean' uses the arithmetic mean; "
					"'inverse-variance' weights measurements by their "
					'uncertainties and therefore requires finite positive '
					'measurement errors.'
				),
				category='TIMESERIES',
				default_value='',
				allowed_values=[
					'mean',
					'inverse-variance',
				]
			),

			'gp-sigma' : ValueOption(
				name='gp-sigma',
				value='',
				value_type=float,
				description=(
					'Gaussian Process kernel amplitude. '
					'If omitted, it is inferred independently for each '
					'time-series channel.'
				),
				category='TIMESERIES',
				default_value='',
				min_value=0.0
			),

			'gp-rho' : ValueOption(
				name='gp-rho',
				value='',
				value_type=float,
				description=(
					'Gaussian Process Matern-3/2 correlation length scale '
					'in timestamp units. If omitted, it is inferred '
					'independently for each time-series channel.'
				),
				category='TIMESERIES',
				default_value='',
				min_value=0.0
			),

			'gp-jitter' : ValueOption(
				name='gp-jitter',
				value='',
				value_type=float,
				description=(
					'Gaussian Process noise floor used when measurement '
					'uncertainties are unavailable. If omitted, the '
					'fextractor default is used.'
				),
				category='TIMESERIES',
				default_value='',
				min_value=0.0
			),
			
			'timeseries-plot' : EnumValueOption(
				name='timeseries-plot',
				value='',
				value_type=str,
				description=(
					'Time-series diagnostic plot mode. '
					"'input' plots the original input series; "
					"'processed' plots the series effectively passed to "
					"the embedding model after preprocessing; "
					"'both' plots input and processed series side by side; "
					"'none' disables diagnostic plotting. "
					'Plots contain one row per channel, with sample/bin '
					'index on the lower x-axis and physical time on the '
					'upper x-axis.'
				),
				category='TIMESERIES',
				default_value='none',
				allowed_values=[
					'none',
					'input',
					'processed',
					'both',
				]
			),
			
			# == TIME SERIES REPRESENTATION OPTIONS ==
			'input-sample-policy' : EnumValueOption(
				name='input-sample-policy',
				value='',
				value_type=str,
				description=(
					'Samples from the prepared time series passed to the '
					'extractor. "observed" uses only measured/bin-observed '
					'samples; "completed" also uses interpolated and '
					'GP-predicted samples.'
				),
				category='REPRESENTATION',
				default_value='observed',
				allowed_values=[
					'observed',
					'completed',
				]
			),
			
			'aggregation' : EnumValueOption(
				name='aggregation',
				value='',
				value_type=str,
				description='Token aggregation used to produce a fixed-size representation',
				category='REPRESENTATION',
				default_value='',
				allowed_values=[
					'mean',
					'std',
					'max',
					'mean_std',
					'mean_max',
					'mean_std_max',
					'last',
					'reg',
					'flatten',
				]
			),

			'context-length' : ValueOption(
				name='context-length',
				value='',
				value_type=int,
				description='Optional maximum model context length',
				category='REPRESENTATION',
				default_value='',
				min_value=1
			),

			# - Backend representation options
			'batch-size' : ValueOption(
				name='batch-size',
				value='',
				value_type=int,
				description='Embedding batch size',
				category='REPRESENTATION',
				default_value='',
				min_value=1
			),
			
			# - MOIRAI backend options
			'patching-mode' : EnumValueOption(
				name='patching-mode',
				value='',
				value_type=str,
				description=(
					'Moirai-2 patching mode. '
					'If omitted, the backend default is used.'
				),
				category='REPRESENTATION',
				default_value='',
				allowed_values=[
					'time_only',
					'time_variate',
				]
			),

			'token-order' : EnumValueOption(
				name='token-order',
				value='',
				value_type=str,
				description=(
					'Moirai-2 token ordering used with time_variate patching. '
					'If omitted, the backend default is used.'
				),
				category='REPRESENTATION',
				default_value='',
				allowed_values=[
					'by_variate',
					'interleave_time',
				]
			),
			
			# - LICU backend options
			'feature-set' : EnumValueOption(
				name='feature-set',
				value='',
				value_type=str,
				description=(
					'LiCu handcrafted feature set. '
					"'basic' selects a compact set of statistical/time-domain "
					"features; 'default' selects the standard fextractor LiCu "
					"feature set; 'full' enables the extended handcrafted "
					"feature set."
				),
				category='REPRESENTATION',
				default_value='',
				allowed_values=[
					'basic',
					'default',
					'full',
				]
			),

			'invalid-feature-policy' : EnumValueOption(
				name='invalid-feature-policy',
				value='',
				value_type=str,
				description=(
					'LiCu policy applied when a selected feature returns a non-finite value. '
					'"zero" replaces the value with 0 and records it in extraction metadata; "error" aborts extraction.'
				),
				category='REPRESENTATION',
				default_value='',
				allowed_values=[
					'zero',
					'error',
				]
			),

			'min-samples' : ValueOption(
				name='min-samples',
				value='',
				value_type=int,
				description=(
					'Minimum number of valid selected samples required per '
					'time-series channel by LiCu handcrafted and ML embedding backends.'
				),
				category='REPRESENTATION',
				default_value='',
				min_value=1
			),
			
			'licu-embed-output' : EnumValueOption(
				name='licu-embed-output',
				value='',
				value_type=str,
				description=(
					'Output representation exposed by LiCu ML embedding models. '
					'Supported values are model-specific: Astromer supports '
					'mean/max/sequence; MOMENT-1 supports mean/sequence; '
					'AstraCLR supports mean; ATAT supports token/mean/sequence; '
					'ATCAT supports last/mean/sequence.'
				),
				category='REPRESENTATION',
				default_value='',
				allowed_values=[
					'mean',
					'max',
					'sequence',
					'token',
					'last',
				]
			),

			'licu-embed-reduction' : EnumValueOption(
				name='licu-embed-reduction',
				value='',
				value_type=str,
				description=(
					'Observation reduction/windowing strategy used by LiCu ML '
					'embedding models. If omitted, the selected model default is used.'
				),
				category='REPRESENTATION',
				default_value='',
				allowed_values=[
					'beginning',
					'end',
					'middle',
					'non-overlapping-windows',
				]
			),			
			
			'licu-mag-zp' : ValueOption(
				name='licu-mag-zp',
				value='',
				value_type=float,
				description=(
					'AB magnitude zero-point associated with input fluxes '
					'for LiCu ATAT/ATCAT models. If omitted, the model '
					'default is used.'
				),
				category='REPRESENTATION',
				default_value=''
			),

			'licu-allow-extra-bands' : Option(
				name='licu-allow-extra-bands',
				description=(
					'Allow LiCu multiband embedding models to ignore '
					'observations whose band labels are not supported by '
					'the selected model.'
				),
				category='REPRESENTATION',
				default_value=False
			),			
			
			# == SAVE OPTIONS ==
			'outfile' : ValueOption(
				name='outfile',
				value='',
				value_type=str, 
				description='Output filename (.json) containing embedding/feature data extracted',
				category='SAVE',
				default_value='fextractor_results.json'
			),
			
			# == RUN OPTIONS ==
			'device' : ValueOption(
				name='device',
				value='',
				value_type=str,
				description='Inference device, for example cuda, cuda:0, or cpu',
				category='RUN',
				default_value='cuda'
			),

			'skip-errors' : Option(
				name='skip-errors',
				description='Skip failed datalist entries instead of aborting the job',
				category='RUN',
				default_value=False
			),

			'no-logredir' : Option(
				name='no-logredir', 
				description='Do not redirect logs to output file in script',
				category='RUN'
			),
		
		} ## close options
		
		
		# - Define dictionary with job outputs produced
		embedding_out_desc = (
			'JSON dictionary containing the input data representation '
			'(embedding/features) extracted by the selected fextractor backend. '
			'For JSON datalist input, the original entries are preserved and '
			'the extracted representation is added to each processed entry.'
		)

		embedding_out_format = (
			'Output JSON follows the general format below:\n\n'
			'{\n'
			'  "data": [\n'
			'    {\n'
			'      "...": "... original input metadata ...",\n'
			'      "feats": [0.12, -0.34, 0.56, ...]\n'
			'    },\n'
			'    ...\n'
			'  ],\n'
			'  "metadata": {\n'
			'    "...": "... extraction and preprocessing metadata ..."\n'
			'  }\n'
			'}\n'
			'\n'
			'where:\n'
			'* data | list(dict): Processed input entries.\n'
			'* feats | list(float): Extracted fixed-size feature/embedding vector.\n'
			'* metadata | dict: Extraction configuration and preprocessing metadata.'
		)

		self.job_outputs= {
			"embeddings-json": {
				"path": None,
				"glob": "*.json",
				"type": "application/json",
				"role": "primary_result",
				"description": embedding_out_desc,
				"format": embedding_out_format,
				"parser": "json",
				"required": True,
				"notes": (
					"The output JSON filename is by default "
					"'fextractor_results.json', but it can be configured "
					"with the option 'outfile'."
				)
			},

			"timeseries-plot": {
				"path": None,
				"glob": "*_timeseries.png",
				"type": "image/png",
				"role": "visualization",
				"description": (
					"Diagnostic visualization of time-series input and/or "
					"preprocessed model input for all channels."
				),
				"format": "",
				"parser": "image",
				"required": False,
				"notes": (
					"Time-series diagnostic PNG files are produced only when "
					"'timeseries-plot' is set to 'input', 'processed', or 'both'. "
					"For datalist input, one PNG file is produced per processed "
					"time-series entry."
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
					"No explicit fextractor log file is produced when "
					"'no-logredir' is enabled."
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
		
		
	def _split_colon_option(self, option_name):
		"""Return a colon-separated option as a stripped list."""

		value = self.job_options.get(option_name, "")

		if not value:
			return []

		return [item.strip() for item in value.split(":")]

		
	def _prepare_boolean_command_options(self, model):
		"""Translate false boolean options to wrapper negative flags."""

		# - Convert regularize=False to --no-regularize
		if (
			model in {
				"chronos2",
				"moirai2",
				"falcon1",
				"licu",
			}
			or model in LICU_EMBED_MODELS
		):
			if "regularize" in self.job_options and self.job_options["regularize"] is False:
				self.cmd_args.append("--no-regularize")

		# - Convert zscale=False to --no-zscale
		if (
			model in IMAGE_MODELS
			and "zscale" in self.job_options
			and self.job_options["zscale"] is False
		):
			self.cmd_args.append("--no-zscale")

	
	def _validation_error(self, message):
		"""Set validation error state, log it, and return False."""

		self.validation_status = message
		logger.warning(message, action="submitjob")

		return False
	
	def _validate_model_modality_options(self, model, requested_options):
		"""Reject image-only/time-series-only options on the wrong modality."""

		# - Validate time-series models
		if model in TIMESERIES_MODELS:
			invalid_options = requested_options & IMAGE_ONLY_OPTIONS

			if invalid_options:
				return self._validation_error(
					"Image-only option(s) not supported by model '%s': %s"
					% (
						model,
						", ".join(sorted(invalid_options)),
					)
				)

		# - Validate image models
		if model in IMAGE_MODELS:
			invalid_options = requested_options & TIMESERIES_ONLY_OPTIONS

			if invalid_options:
				return self._validation_error(
					"Time-series-only option(s) not supported by model '%s': %s"
					% (
						model,
						", ".join(sorted(invalid_options)),
					)
				)

		return True

		
	def _validate_timeseries_profile(self, model):
		"""Validate preprocessing-profile support for time-series models."""

		# - Define models restricted to the default preprocessing profile
		default_profile_only_models = {
			"chronos2",
			"moirai2",
			"falcon1",
			"licu",
		} | LICU_EMBED_MODELS

		# - Skip validation for unrelated models
		if model not in default_profile_only_models:
			return True

		# - Validate preprocessing profile
		profile = self.job_options.get("preproc-profile", "default")

		if profile != "default":
			return self._validation_error(
				"Time-series model '%s' currently supports only the "
				"'default' preprocessing profile"
				% model
			)

		return True


	def _validate_regularization_options(self, model, requested_options):
		"""Validate common time-series regularization option combinations."""

		# - Define models supporting common regularization options
		regularization_models = {
			"chronos2",
			"moirai2",
			"falcon1",
			"licu",
		} | LICU_SINGLE_CHANNEL_EMBED_MODELS

		# - Skip validation for unrelated models
		if model not in regularization_models:
			return True

		# - Resolve regularization method
		regularization_method = self.job_options.get("regularization-method", "bin")

		if not regularization_method:
			regularization_method = "bin"

		# - Validate GP-only options
		gp_only_options = {
			"gp-sigma",
			"gp-rho",
			"gp-jitter",
		}

		invalid_options = requested_options & gp_only_options

		if invalid_options and regularization_method != "gp":
			return self._validation_error(
				"Gaussian-Process option(s) require "
				"'regularization-method=gp': %s"
				% ", ".join(sorted(invalid_options))
			)

		# - Validate bin-only options
		bin_only_options = {
			"missing-strategy",
			"bin-aggregation",
		}

		invalid_options = requested_options & bin_only_options

		if invalid_options and regularization_method == "gp":
			return self._validation_error(
				"Bin-regularization option(s) are not used with "
				"'regularization-method=gp': %s"
				% ", ".join(sorted(invalid_options))
			)

		# - Validate GP cadence requirement
		regularize = self.job_options.get("regularize", False)

		if regularization_method == "gp" and regularize and not self.job_options.get("cadence"):
			return self._validation_error(
				"GP regularization requires an explicit 'cadence'"
			)

		# - Validate GP input-sample policy
		input_sample_policy = self.job_options.get("input-sample-policy", "observed")

		if (
			regularize
			and regularization_method == "gp"
			and input_sample_policy == "observed"
		):
			return self._validation_error(
				"GP regularization requires "
				"'input-sample-policy=completed' because the "
				"regularized series consists of GP predictions."
			)

		return True
	
	
	def _validate_chronos_options(self, model, requested_options):
		"""Validate Chronos-specific option compatibility."""

		# - Skip validation for unrelated models
		if model != "chronos2":
			return True

		# - Validate unsupported options
		invalid_options = requested_options & (
			MOIRAI_ONLY_OPTIONS
			| LICU_ALL_OPTIONS
		)

		if invalid_options:
			return self._validation_error(
				"Option(s) not supported by model '%s': %s"
				% (
					model,
					", ".join(sorted(invalid_options)),
				)
			)

		return True

	
	def _validate_moirai_options(self, model, requested_options):
		"""Validate Moirai-specific option compatibility."""

		# - Skip validation for unrelated models
		if model != "moirai2":
			return True

		# - Validate unsupported options
		invalid_options = requested_options & (
			MOIRAI_UNSUPPORTED_COMMON_OPTIONS
			| LICU_ALL_OPTIONS
		)		

		if invalid_options:
			return self._validation_error(
				"Option(s) not supported by model '%s': %s"
				% (
					model,
					", ".join(sorted(invalid_options)),
				)
			)

		return True

	def _validate_falcon_options(self, model, requested_options):
		"""Validate Falcon-1-specific option compatibility."""

		# - Skip validation for unrelated models
		if model != "falcon1":
			return True

		# - Validate unsupported options
		invalid_options = requested_options & FALCON_UNSUPPORTED_OPTIONS

		if invalid_options:
			return self._validation_error(
				"Option(s) not supported by model '%s': %s"
				% (
					model,
					", ".join(sorted(invalid_options)),
				)
			)

		# - Falcon-1 does not expose a REG token
		if self.job_options.get("aggregation", "") == "reg":
			return self._validation_error(
				"'aggregation=reg' is not supported by model 'falcon1' "
				"because Falcon-1 does not expose a REG token"
			)

		return True	
	
	def _validate_licu_handcrafted_options(self, model, requested_options):
		"""Validate handcrafted LiCu option compatibility."""

		# - Skip validation for unrelated models
		if model != "licu":
			return True

		# - Validate unsupported options
		invalid_options = requested_options & (
			LICU_HANDCRAFTED_UNSUPPORTED_OPTIONS
			| LICU_EMBED_ONLY_OPTIONS
			| LICU_MULTIBAND_ONLY_OPTIONS
		)

		if invalid_options:
			return self._validation_error(
				"Option(s) not supported by LiCu handcrafted "
				"feature extraction: %s"
				% ", ".join(sorted(invalid_options))
			)

		return True


	def _validate_licu_embed_options(self, model, requested_options):
		"""Validate common LiCu ML embedding options."""

		# - Skip validation for unrelated models
		if model not in LICU_EMBED_MODELS:
			return True

		# - Build unsupported option set
		unsupported_options = set(LICU_EMBED_UNSUPPORTED_OPTIONS)

		if model in LICU_SINGLE_CHANNEL_EMBED_MODELS:
			unsupported_options |= LICU_MULTIBAND_ONLY_OPTIONS

		# - Validate unsupported options
		invalid_options = requested_options & unsupported_options

		if invalid_options:
			return self._validation_error(
				"Option(s) not supported by LiCu ML embedding "
				"model '%s': %s"
				% (
					model,
					", ".join(sorted(invalid_options)),
				)
			)

		# - Validate model-specific embedding output
		embed_output = self.job_options.get("licu-embed-output", "")

		if embed_output and embed_output not in LICU_MODEL_OUTPUTS[model]:
			return self._validation_error(
				"'licu-embed-output=%s' is not supported by "
				"LiCu model '%s'. Supported outputs: %s"
				% (
					embed_output,
					model,
					", ".join(sorted(LICU_MODEL_OUTPUTS[model])),
				)
			)

		return True
		
	def _validate_licu_multiband_options(self, model, requested_options):
		"""Validate LiCu multiband model input requirements."""

		# - Skip validation for unrelated models
		if model not in LICU_MULTIBAND_EMBED_MODELS:
			return True

		# - Validate time-series layout
		layout = self.job_options.get("timeseries-layout", "long")

		if not layout:
			layout = "long"

		if layout != "long":
			return self._validation_error(
				"LiCu multiband embedding model '%s' requires "
				"'timeseries-layout=long'"
				% model
			)

		# - Validate value columns
		value_columns = self.job_options.get("value-columns", "")

		if not value_columns:
			return self._validation_error(
				"LiCu multiband embedding model '%s' requires "
				"exactly one 'value-columns' field"
				% model
			)

		value_column_list = self._split_colon_option("value-columns")

		if len(value_column_list) != 1 or not value_column_list[0]:
			return self._validation_error(
				"LiCu multiband embedding model '%s' requires "
				"exactly one value field"
				% model
			)

		# - Validate error columns
		error_columns = self._split_colon_option("error-columns")

		if len(error_columns) > 1 or any(not item for item in error_columns):
			return self._validation_error(
				"LiCu multiband embedding model '%s' accepts at most "
				"one 'error-columns' field"
				% model
			)

		if model in {"astra-clr", "atcat"} and len(error_columns) != 1:
			return self._validation_error(
				"LiCu multiband embedding model '%s' requires "
				"exactly one 'error-columns' field"
				% model
			)

		# - Validate photometric band input
		band_column = self.job_options.get("band-column", "")
		band_key = self.job_options.get("band-key", "")

		if not band_column and not band_key:
			return self._validation_error(
				"LiCu multiband embedding model '%s' requires "
				"'band-column' for tabular input or 'band-key' "
				"for inline JSON input"
				% model
			)

		# - Validate timestamp input
		time_column = self.job_options.get("time-column", "")
		time_start_key = self.job_options.get("time-start-key", "")
		cadence_key = self.job_options.get("cadence-key", "")

		if bool(time_start_key) != bool(cadence_key):
			return self._validation_error(
				"'time-start-key' and 'cadence-key' must be supplied together"
			)

		if time_column and (time_start_key or cadence_key):
			return self._validation_error(
				"LiCu multiband input must use either 'time-column' or "
				"'time-start-key'+'cadence-key', not both"
			)

		if not time_column and not (time_start_key and cadence_key):
			return self._validation_error(
				"LiCu multiband embedding model '%s' requires "
				"explicit timestamps via 'time-column' or regular "
				"timestamps via 'time-start-key'+'cadence-key'"
				% model
			)

		# - Reject time-series regularization
		if self.job_options.get("regularize", False):
			return self._validation_error(
				"LiCu multiband embedding model '%s' does not support "
				"time-series regularization"
				% model
			)

		# - Reject regularization-specific options
		regularization_options = {
			"cadence",
			"regularization-method",
			"missing-strategy",
			"bin-aggregation",
			"gp-sigma",
			"gp-rho",
			"gp-jitter",
		}

		invalid_options = requested_options & regularization_options

		if invalid_options:
			return self._validation_error(
				"Regularization option(s) are not supported by LiCu "
				"multiband embedding model '%s': %s"
				% (
					model,
					", ".join(sorted(invalid_options)),
				)
			)

		# - Validate magnitude zero-point option
		if "licu-mag-zp" in requested_options and model not in {"atat", "atcat"}:
			return self._validation_error(
				"'licu-mag-zp' is supported only by LiCu models "
				"'atat' and 'atcat'"
			)

		return True	


	def _validate_fats_options(self, model, requested_options, data_inputs):
		"""Validate FATS options and input layout."""

		# - Skip validation for unrelated models
		if model != "fats":
			return True

		# - Validate common FATS options and input type
		if not self._validate_fats_common_options(requested_options, data_inputs):
			return False

		# - Resolve input extension and layout
		input_ext = os.path.splitext(str(data_inputs))[1].lower()
		layout = self.job_options.get("timeseries-layout", "long")

		if not layout:
			layout = "long"

		# - Validate JSON input
		if input_ext == ".json":
			return self._validate_fats_json_input(layout)

		# - Validate long-layout CSV input
		if layout == "long":
			return self._validate_fats_long_input()

		# - Validate wide-layout CSV input
		if layout == "wide":
			return self._validate_fats_wide_input()

		# - Reject unknown layouts
		return self._validation_error(
			"Unsupported FATS time-series layout '%s'" % layout
		)
		
	
		
	def _validate_fats_common_options(self, requested_options, data_inputs):
		"""Validate options and input types common to all FATS layouts."""

		# - Define unsupported options
		unsupported_options = {
			"preproc-profile",
			"label-column",
			"metadata-columns",
			"regularize",
			"regularization-method",
			"cadence",
			"missing-strategy",
			"bin-aggregation",
			"gp-sigma",
			"gp-rho",
			"gp-jitter",
			"aggregation",
			"context-length",
			"batch-size",
			"patching-mode",
			"token-order",
			"device",
			"skip-errors",
			"timeseries-plot",
			"feature-set",
			"invalid-feature-policy",
			"min-samples",
			"licu-embed-output",
			"licu-embed-reduction",
			"licu-mag-zp",
			"licu-allow-extra-bands",
			"band-column",
			"band-key",
			"input-sample-policy",
		}

		# - Validate unsupported options
		invalid_options = requested_options & unsupported_options

		if invalid_options:
			return self._validation_error(
				"Option(s) not supported by FATS: %s"
				% ", ".join(sorted(invalid_options))
			)

		# - Validate number of inputs
		if isinstance(data_inputs, list):
			return self._validation_error(
				"FATS expects one input CSV file or one JSON datalist per job"
			)

		# - Validate input format
		input_ext = os.path.splitext(str(data_inputs))[1].lower()

		if input_ext not in {".csv", ".json"}:
			return self._validation_error(
				"FATS supports CSV or JSON input, got '%s'" % input_ext
			)

		return True


	def _validate_named_list(self, option_name, label, required=False):
		"""Validate and return one colon-separated option list."""

		# - Read option value
		value = self.job_options.get(option_name, "")

		# - Handle omitted option
		if not value:
			if required:
				self._validation_error(
					"%s requires '%s'" % (label, option_name)
				)
				return None

			return []

		# - Parse list
		items = self._split_colon_option(option_name)

		# - Validate empty names
		if any(not item for item in items):
			self._validation_error(
				"%s '%s' contains an empty name" % (label, option_name)
			)
			return None

		# - Validate duplicate names
		if len(set(items)) != len(items):
			self._validation_error(
				"%s '%s' contains duplicate names" % (label, option_name)
			)
			return None

		return items
		
	def _validate_fats_json_input(self, layout):
		"""Validate FATS JSON datalist input options."""

		# - Validate value fields
		value_columns = self._validate_named_list("value-columns", "FATS")

		if value_columns is None:
			return False

		# - Validate error fields
		error_columns = self._validate_named_list("error-columns", "FATS")

		if error_columns is None:
			return False

		# - Validate logical channel names
		channel_names = self._validate_named_list("channel-names", "FATS")

		if channel_names is None:
			return False

		# - Validate timestamp definition
		time_column = self.job_options.get("time-column", "")
		time_start_key = self.job_options.get("time-start-key", "")
		cadence_key = self.job_options.get("cadence-key", "")

		if bool(time_start_key) != bool(cadence_key):
			return self._validation_error(
				"FATS inline JSON requires both "
				"'time-start-key' and 'cadence-key'"
			)

		if time_column and (time_start_key or cadence_key):
			return self._validation_error(
				"FATS inline JSON must use either "
				"'time-column' or 'time-start-key'+'cadence-key', not both"
			)

		# - Validate value/error field cardinality
		if error_columns:
			if not value_columns:
				return self._validation_error(
					"FATS 'error-columns' requires "
					"'value-columns' for inline JSON input"
				)

			if len(error_columns) != len(value_columns):
				return self._validation_error(
					"FATS requires one error field per value field "
					"(%d value fields, %d error fields)"
					% (
						len(value_columns),
						len(error_columns),
					)
				)

		# - Validate channel-name cardinality
		if channel_names:
			if value_columns:
				if len(channel_names) != len(value_columns):
					return self._validation_error(
						"FATS requires one channel name per value field "
						"(%d value fields, %d channel names)"
						% (
							len(value_columns),
							len(channel_names),
						)
					)

			elif layout == "wide":
				value_prefixes = self._split_colon_option("value-prefixes")

				if value_prefixes and len(channel_names) != len(value_prefixes):
					return self._validation_error(
						"FATS requires one channel name per "
						"value prefix (%d value prefixes, %d channel names)"
						% (
							len(value_prefixes),
							len(channel_names),
						)
					)

		return True							
	
	def _validate_fats_long_input(self):
		"""Validate FATS long-layout CSV input."""

		# - Validate value columns
		value_columns = self._validate_named_list(
			"value-columns",
			"FATS",
			required=True,
		)

		if value_columns is None:
			return False

		# - Validate error columns
		error_columns = self._validate_named_list("error-columns", "FATS")

		if error_columns is None:
			return False

		# - Validate channel names
		channel_names = self._validate_named_list("channel-names", "FATS")

		if channel_names is None:
			return False

		# - Validate error-column requirements
		if error_columns:
			if not self.job_options.get("time-column", ""):
				return self._validation_error(
					"FATS requires 'time-column' when 'error-columns' are provided"
				)

			if len(error_columns) != len(value_columns):
				return self._validation_error(
					"FATS requires one error column per value column "
					"(%d value columns, %d error columns)"
					% (
						len(value_columns),
						len(error_columns),
					)
				)

		# - Validate channel-name cardinality
		if channel_names and len(channel_names) != len(value_columns):
			return self._validation_error(
				"FATS requires one channel name per value column "
				"(%d value columns, %d channel names)"
				% (
					len(value_columns),
					len(channel_names),
				)
			)

		return True
	
	def _validate_fats_wide_input(self):
		"""Validate FATS wide-layout CSV input."""

		# - Validate value prefixes
		value_prefixes = self._validate_named_list(
			"value-prefixes",
			"FATS",
			required=True,
		)

		if value_prefixes is None:
			return False

		# - Validate error prefixes
		error_prefixes = self._validate_named_list("error-prefixes", "FATS")

		if error_prefixes is None:
			return False

		# - Validate channel names
		channel_names = self._validate_named_list("channel-names", "FATS")

		if channel_names is None:
			return False

		# - Validate error-prefix cardinality
		if error_prefixes and len(error_prefixes) != len(value_prefixes):
			return self._validation_error(
				"FATS requires one error prefix per value prefix "
				"(%d value prefixes, %d error prefixes)"
				% (
					len(value_prefixes),
					len(error_prefixes),
				)
			)

		# - Validate channel-name cardinality
		if channel_names and len(channel_names) != len(value_prefixes):
			return self._validation_error(
				"FATS requires one channel name per value prefix "
				"(%d value prefixes, %d channel names)"
				% (
					len(value_prefixes),
					len(channel_names),
				)
			)

		# - Validate timestamp definition
		time_prefix = self.job_options.get("time-prefix", "")
		time_start_column = self.job_options.get("time-start-column", "")
		cadence_column = self.job_options.get("cadence-column", "")

		if time_prefix and (time_start_column or cadence_column):
			return self._validation_error(
				"FATS wide-layout input must use either "
				"'time-prefix' or "
				"'time-start-column'+'cadence-column', not both"
			)

		if bool(time_start_column) != bool(cadence_column):
			return self._validation_error(
				"'time-start-column' and 'cadence-column' must be supplied together"
			)

		return True	
		
	def _resolve_container_variant(self, model):
		"""Resolve and store the runtime container variant."""

		# - Validate model/container mapping
		if model not in MODEL_CONTAINER_VARIANTS:
			return self._validation_error(
				"Cannot determine container variant for model '%s'" % model
			)

		# - Store resolved container variant
		self.run_options["container_variant"] = MODEL_CONTAINER_VARIANTS[model]

		return True		
	
	def validate(self, job_options, data_inputs):
		"""Validate fextractor inputs and resolve the runtime container."""

		# - Collect explicitly requested options
		requested_options = set(job_options.keys())

		# - Run base configurator validation
		if not AppConfigurator.validate(self, job_options, data_inputs):
			return False

		# - Resolve selected model
		model = self.job_options.get("model", "simclr_radio")

		# - Prepare wrapper-specific boolean options
		self._prepare_boolean_command_options(model)

		# - Validate model modality options
		if not self._validate_model_modality_options(model, requested_options):
			return False

		# - Validate time-series preprocessing profile
		if not self._validate_timeseries_profile(model):
			return False

		# - Validate common regularization options
		if not self._validate_regularization_options(model, requested_options):
			return False

		# - Validate Chronos options
		if not self._validate_chronos_options(model, requested_options):
			return False

		# - Validate Moirai options
		if not self._validate_moirai_options(model, requested_options):
			return False
			
		# - Validate Falcon options
		if not self._validate_falcon_options(model, requested_options):
			return False			

		# - Validate handcrafted LiCu options
		if not self._validate_licu_handcrafted_options(model, requested_options):
			return False

		# - Validate LiCu ML embedding options
		if not self._validate_licu_embed_options(model, requested_options):
			return False

		# - Validate LiCu multiband input options
		if not self._validate_licu_multiband_options(model, requested_options):
			return False		
		
		# - Validate FATS options and input layout
		if not self._validate_fats_options(model, requested_options, data_inputs):
			return False

		# - Resolve runtime container
		return self._resolve_container_variant(model)
