"""CAESAR-REST configurator for the OXKAT Measurement Set pipeline.

Supported stages:
- GET_INFO: inspect a Measurement Set and generate observation metadata.
- 1GC: prepare the first-generation calibration recipe using a Measurement
  Set and the project_info.json artifact from a completed GET_INFO run.

The 1GC stage currently generates the calibration execution script but does
not execute the scientific calibration steps.

For V2 pipeline submissions, inputs are resolved from registered datasets
and retained upstream artifacts. The Measurement Set is staged as a
read-only reference. Actual calibration will require a private writable
copy of the Measurement Set.

Later calibration and imaging stages remain unsupported.
"""

import os
import base64
import json
import math
import re

from caesar_rest.app_configurators.base import (
	AppConfigurator,
	EnumValueOption,
)
from caesar_rest import logger


OXKAT_STAGES = [
	"GET_INFO",
	"1GC",
	"FLAG",
	"2GC",
	"3GC_PEEL",
	"3GC_FACET",
]

# Keep synchronized with run_oxkat.sh. Do not allow unimplemented stages to
# reach Slurm: they require distinct inputs, output contracts and permissions.
IMPLEMENTED_STAGES = {"GET_INFO", "1GC"}


# - Scientific settings exposed by OXKAT's upstream config.py.
# - Keep this policy inside the application configurator, not the
#   generic V2 pipeline submission implementation.
OXKAT_CONFIG_OPTIONS = {
	"CAL_1GC_PRIMARY": {
		"type": "field_selection",
		"stages": {"GET_INFO"},
	},
	"CAL_1GC_SECONDARIES": {
		"type": "field_selection",
		"stages": {"GET_INFO"},
	},
	"CAL_1GC_TARGETS": {
		"type": "field_selection",
		"stages": {"GET_INFO"},
	},
	"PRE_NCHANS": {
		"type": "integer",
		"stages": {"1GC"},
		"min": 1,
		"max": 65536,
	},
	"WSC_CIRCULARBEAM": {
		"type": "boolean",
		"stages": {"FLAG", "2GC", "3GC_PEEL", "3GC_FACET"},
	},
	"WSC_NITER": {
		"type": "integer",
		"stages": {"FLAG", "2GC", "3GC_PEEL", "3GC_FACET"},
		"min": 0,
		"max": 10000000,
	},
	"WSC_BRIGGS": {
		"type": "number",
		"stages": {"FLAG", "2GC", "3GC_PEEL", "3GC_FACET"},
		"min": -2.0,
		"max": 2.0,
	},
}

_FIELD_SELECTION = re.compile(r'^(?:auto|[0-9]+(?:,[0-9]+)*)$')

##################################################
###     APP CONFIG CLASS
##################################################
class OxkatAppConfigurator(AppConfigurator):
	"""Validate oxkat requests and create the runner's application arguments."""

	def __init__(self, app_name="oxkat"):
		super().__init__(app_name=app_name)

		# Informational command name for the CAESAR-REST application registry.
		# Kubernetes/Slurm launches the image's run_job.sh entrypoint.
		self.cmd = "run_oxkat.sh"
		self.cmd_args = []
		self.batch_processing_support = False

		self.description = (
			"Process MeerKAT radio-interferometric Measurement Sets using OXKAT. "
			"The GET_INFO stage inspects an observation and generates metadata "
			"describing the observing band, fields, calibrators and targets. "
			"The 1GC stage consumes this metadata together with the original "
			"Measurement Set to prepare the first-generation calibration recipe. "
			"Currently, 1GC generates and validates its execution script without "
			"performing calibration. Subsequent calibration and imaging stages "
			"will be enabled incrementally."
		)
		
		self.tool_categories = ["measurement-set"]
		
		self.input_requirements = {
			"supported_formats": ["ms"],
			"expected_data": (
				"GET_INFO requires one registered MeerKAT Measurement Set "
				"directory (*.ms). "
				"1GC additionally requires project_info.json produced by "
				"a completed upstream GET_INFO pipeline run."
			),
			"notes": [
				"Measurement Sets are registered server-side and are not uploaded.",
				"V2 pipeline runs reference the Measurement Set using dataset_id.",
				"GET_INFO uses a read-only reference without copying the dataset.",
				"1GC requires the registered Measurement Set and the retained "
				"project_info artifact from GET_INFO.",
				"CAESAR-REST resolves V2 inputs using trusted dataset and "
				"artifact bindings; filesystem paths are not supplied by clients.",
				"During 1GC preparation, the original Measurement Set is "
				"not modified."
			],
		}
		
		self.limitations = [
			"GET_INFO and 1GC preparation are the currently supported stages.",
			"1GC preparation generates the calibration execution script but "
			"does not execute calibration.",
			"Exactly one registered Measurement Set is supported per V2 run.",
			"1GC requires project_info.json from a completed GET_INFO run.",
			"The Measurement Set must be accessible to the Slurm execution environment.",
			"Actual 1GC calibration requires a private writable Measurement Set copy.",
			"FLAG, 2GC, 3GC_PEEL and 3GC_FACET are not yet supported."
		]
		
		# - Set valid options
		self.valid_options = {
			"stage": EnumValueOption(
				name="stage",
				value="",
				value_type=str,
				description=(
					"OXKAT processing stage. GET_INFO executes observation metadata "
					"extraction; 1GC prepares the first-generation calibration recipe "
					"without executing calibration. Other stages are reserved for "
					"future implementation."
				),
				category="RUN",
				default_value="GET_INFO",
				allowed_values=OXKAT_STAGES,
			),
		}
		
		# - Describe job output
		self.job_outputs = {
			"manifest": {
				"path": "oxkat_manifest.json",
				"glob": None,
				"type": "application/json",
				"role": "primary_result",
				"description": "Stage status and relative artifact references.",
				"format": "",
				"parser": "json",
				"required": True,
				"notes": "Contains portable output names, not internal absolute paths.",
			},
			"project_info": {
				"path": "project_info.json",
				"glob": None,
				"type": "application/json",
				"role": "primary_result",
				"description": (
					"Observation metadata generated by GET_INFO and "
					"propagated to downstream 1GC preparation."
				),
				"format": "",
				"parser": "json",
				"required": True,
				"notes": (
					"Contains observing band, Measurement Set identity, "
					"field and calibrator metadata."
				),
			},
			"preparation_script": {
				"path": "submit_1GC_jobs.sh",
				"glob": None,
				"type": "text/x-shellscript",
				"role": "diagnostic",
				"description": (
					"Generated first-generation calibration script. "
					"Produced during 1GC preparation but not executed."
				),
				"format": "",
				"parser": "",
				"required": False,
			},
			"working_measurement_sets": {
				"path": None,
				"glob": "*.ms",
				"kind": "directory",
				"type": "application/x-casa-measurement-set",
				"role": "primary_result",
				"description": (
					"Private derived Measurement Sets produced by "
					"first-generation calibration."
				),
				"required": False,
			},
			"measurement_set_flagversions": {
				"path": None,
				"glob": "*.ms.flagversions",
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "auxiliary",
				"description": (
					"CASA flag-version histories associated with "
					"derived Measurement Sets."
				),
				"required": False,
			},
			"gain_tables": {
				"path": "GAINTABLES",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "primary_result",
				"description": "First-generation calibration solution tables.",
				"required": False,
			},
			"gain_plots": {
				"path": "GAINPLOTS",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "diagnostic",
				"description": "Plots of calibration solutions.",
				"required": False,
			},
			"visibility_plots": {
				"path": "VISPLOTS",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "diagnostic",
				"description": "Diagnostic visibility plots.",
				"required": False,
			},			
			"oxkat_config_overrides": {
				"path": "oxkat_config_overrides.json",
				"glob": None,
				"type": "application/json",
				"role": "diagnostic",
				"description": (
					"Validated OXKAT scientific overrides requested "
					"for this pipeline stage."
				),
				"format": "",
				"parser": "json",
				"required": False,
			},
			"log": {
				"path": None,
				"glob": "*.log",
				"type": "text/plain",
				"role": "diagnostic",
				"description": "Oxkat and CAESAR execution logs.",
				"format": "",
				"parser": "text",
				"required": False,
				"notes": "Diagnostic artifacts can disclose internal paths; restrict access.",
			},
		}
		self.option_value_transformer = {}



	def validate_pipeline_options(self, job_options):
		"""Validate optional stage-specific upstream OXKAT settings."""

		if not isinstance(job_options, dict):
			raise ValueError('job_options must be an object')

		stage = job_options.get('stage')

		if stage not in IMPLEMENTED_STAGES:
			raise ValueError('OXKAT stage is not implemented: %s' % stage)

		unknown = set(job_options) - {'stage', 'oxkat_config'}

		if unknown:
			raise ValueError(
				'Unsupported OXKAT job options: %s' %
				', '.join(sorted(unknown))
			)

		if 'oxkat_config' not in job_options:
			return None

		overrides = job_options['oxkat_config']

		if not isinstance(overrides, dict):
			raise ValueError('oxkat_config must be an object')

		if not overrides:
			raise ValueError('oxkat_config must not be empty')

		if len(overrides) > 32:
			raise ValueError('Too many OXKAT configuration overrides')

		validated = {}

		for name, value in overrides.items():
			if not isinstance(name, str):
				raise ValueError('OXKAT configuration names must be strings')

			spec = OXKAT_CONFIG_OPTIONS.get(name)

			if spec is None:
				raise ValueError(
					'Unsupported OXKAT configuration option: %s' % name
				)

			if stage not in spec['stages']:
				raise ValueError(
					'OXKAT option %s is not applicable to stage %s' %
					(name, stage)
				)

			value_type = spec['type']

			if value_type == 'boolean':
				if type(value) is not bool:
					raise ValueError('%s requires a boolean' % name)

			elif value_type == 'integer':
				if type(value) is not int:
					raise ValueError('%s requires an integer' % name)

			elif value_type == 'number':
				if type(value) not in (int, float):
					raise ValueError('%s requires a number' % name)

				value = float(value)

				if not math.isfinite(value):
					raise ValueError('%s must be finite' % name)

			elif value_type == 'field_selection':
				if (
					not isinstance(value, str)
					or len(value) > 128
					or not _FIELD_SELECTION.fullmatch(value)
				):
					raise ValueError(
						'%s requires auto or comma-separated field IDs' %
						name
					)

			else:
				raise ValueError('Invalid OXKAT option specification')

			if value_type in ('integer', 'number'):
				if value < spec['min'] or value > spec['max']:
					raise ValueError(
						'%s is outside the allowed range' % name
					)

			validated[name] = value

		return validated


	def build_pipeline_arguments(self, parameters, allowed, scalar_validator):
		"""Validate and encode scientific options for a V2 pipeline run."""

		overrides = self.validate_pipeline_options(parameters)

		# - Preserve existing generic validation for scalar V2 arguments.
		scalar_parameters = dict(parameters)
		scalar_parameters.pop('oxkat_config', None)

		args = scalar_validator(scalar_parameters, allowed)

		if overrides is None:
			return args

		document = {
			'stage': scalar_parameters['stage'],
			'overrides': overrides,
		}

		serialized = json.dumps(
			document,
			sort_keys=True,
			separators=(',', ':'),
			allow_nan=False
		).encode('utf-8')

		token = base64.urlsafe_b64encode(serialized).decode('ascii')
		token = token.rstrip('=')

		if len(token) > 3000:
			raise ValueError('Encoded OXKAT configuration is too large')

		args.append('--oxkat-config=%s' % token)

		return args


	def set_data_input_option_value(self):
		"""Translate the one resolved dataset path into the runner's MS option."""
		self.cmd_args.append("--input-ms=%s" % self.data_inputs)

	def validate(self, job_options, data_inputs):
		"""Reject unsupported stages and unsafe/multiple input paths."""
		
		# - Legacy V1 submissions do not support upstream artifact bindings.
		# - 1GC requires project_info.json from a completed GET_INFO run.
		# - V2 submissions use the separate trusted pipeline staging path.
		if isinstance(job_options, dict) and job_options.get("stage") == "1GC":
			self.validation_status = (
				"OXKAT 1GC is supported only through V2 pipeline submission. "
				"Reserve a pipeline run with a registered Measurement Set "
				"and the retained project_info artifact from GET_INFO."
			)
			logger.warning(self.validation_status)
			return False
		
		if not isinstance(data_inputs, str):
			logger.warning("oxkat requires exactly one Measurement Set path")
			return False

		if not os.path.isabs(data_inputs) or not data_inputs.endswith(".ms"):
			logger.warning("oxkat input must be an absolute *.ms directory path")
			return False

		# Do not accept paths with spaces: run_job.sh currently splits the
		# assembled --jobargs string on whitespace.
		if any(ch.isspace() for ch in data_inputs):
			logger.warning("oxkat input paths cannot contain whitespace")
			return False


		# - Reject unknown application options.
		# - In particular, server-controlled execution policies must
		#   never be accepted as scientific job options.
		if isinstance(job_options, dict):
			unknown_options = set(job_options) - set(self.valid_options)

			if unknown_options:
				self.validation_status = (
					"Unsupported oxkat job option(s): %s" %
					", ".join(sorted(unknown_options))
				)
				logger.warning(self.validation_status)
				return False



		if not AppConfigurator.validate(self, job_options, data_inputs):
			return False


		stage = self.job_options.get("stage") or "GET_INFO"

		if stage not in IMPLEMENTED_STAGES:
			self.validation_status = (
				"Oxkat stage '%s' is not yet implemented." % stage
			)
			logger.warning(self.validation_status)
			return False

		# - Select the input staging strategy.
		# - GET_INFO only inspects the Measurement Set and must not
		#   create an unnecessary private copy of a large dataset.
		# - This is trusted application configuration, not a
		#   client-supplied staging option.
		self.run_options["input_staging_mode"] = "reference_ro"

		# - Slurm runs one controller process, not one entire
		#   runner per MPI rank. Leave resource settings to
		#   existing defaults for the first stage.
		return True

