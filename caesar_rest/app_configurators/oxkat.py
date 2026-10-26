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
from caesar_rest.app_configurators import oxkat_scientific_config
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
IMPLEMENTED_STAGES = {"GET_INFO", "1GC", "FLAG"}

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
			"Process MeerKAT radio-interferometric Measurement Sets "
			"using OXKAT. GET_INFO extracts observation metadata; "
			"1GC performs reference calibration and produces calibrated "
			"target Measurement Sets; FLAG performs target flagging, "
			"initial imaging and mask generation using retained "
			"1GC outputs. Subsequent calibration and imaging stages "
			"will be enabled incrementally."
		)		
		
		self.tool_categories = ["measurement-set"]
		
		self.input_requirements = {
			"supported_formats": ["ms"],
			"expected_data": (
				"GET_INFO requires one registered MeerKAT Measurement "
				"Set directory (*.ms). "
				"1GC requires the original registered Measurement Set "
				"and retained project_info.json from GET_INFO. "
				"FLAG requires a calibrated target Measurement Set "
				"produced and retained by 1GC, together with "
				"project_info.json describing the target. "
				"FLAG currently supports one target MS per run."
			),
			"notes": [
				"Measurement Sets are registered server-side; "
				"large scientific datasets are not uploaded.",
				"GET_INFO references the original dataset using "
				"dataset_id and does not modify it.",
				"1GC uses the registered original Measurement Set "
				"and the retained GET_INFO project_info artifact.",
				"1GC performs calibration in a private workspace "
				"and publishes derived Measurement Sets.",
				"FLAG uses two retained upstream artifact bindings: "
				"target_ms and project_info.",
				"FLAG requires a private writable copy of the "
				"calibrated target MS; retained upstream data "
				"must remain unchanged.",
				"FLAG does not require dataset_id because its "
				"Measurement Set is an upstream pipeline artifact.",
				"V2 inputs are resolved from authorized dataset IDs "
				"and frozen artifact bindings; clients do not "
				"supply filesystem paths.",
			],
		}
		
		
		self.limitations = [
			"GET_INFO, 1GC and FLAG are supported through V2 pipelines.",
			"1GC requires a registered original Measurement Set and "
			"the retained project_info artifact from GET_INFO.",
			"FLAG requires a retained calibrated target Measurement Set "
			"from 1GC and validated project_info metadata.",
			"FLAG initially supports one target Measurement Set per run.",
			"Derived Measurement Sets are processed in private writable "
			"workspaces; original datasets and retained upstream artifacts "
			"must not be modified.",
			"2GC, 3GC_PEEL and 3GC_FACET are not yet supported."
		]

		
		# - Set valid options
		self.valid_options = {
			"stage": EnumValueOption(
				name="stage",
				value="",
				value_type=str,
				description=(
					"OXKAT processing stage. GET_INFO extracts observation "
					"metadata; 1GC executes reference calibration and "
					"produces calibrated target Measurement Sets; "
					"FLAG performs target flagging, initial imaging "
					"and cleaning-mask generation using retained "
					"1GC products. 2GC and 3GC stages are reserved "
					"for future implementation."
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
				"stages": ["1GC"],
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
				"stages": ["1GC"],
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
				"stages": ["1GC","FLAG"],
				"required": False,
			},
			"gain_tables": {
				"path": "GAINTABLES",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "primary_result",
				"description": "First-generation calibration solution tables.",
				"stages": ["1GC"],
				"required": False,
			},
			"gain_plots": {
				"path": "GAINPLOTS",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "diagnostic",
				"description": "Plots of calibration solutions.",
				"stages": ["1GC"],
				"required": False,
			},
			"visibility_plots": {
				"path": "VISPLOTS",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "diagnostic",
				"description": "Diagnostic visibility plots.",
				"stages": ["1GC"],
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
			"flag_execution_script": {
				"path": "submit_flag_jobs.sh",
				"glob": None,
				"type": "text/x-shellscript",
				"role": "diagnostic",
				"description": "Generated OXKAT FLAG execution script.",
				"stages": ["FLAG"],
				"required": False,
			},
			"flag_images": {
				"path": "IMAGES",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "primary_result",
				"description": (
					"FLAG imaging products, including initial FITS masks."
				),
				"stages": ["FLAG"],
				"required": False,
			},
			"flagged_target_measurement_sets": {
				"path": None,
				"glob": "*.ms",
				"kind": "directory",
				"type": "application/x-casa-measurement-set",
				"role": "primary_result",
				"description": (
					"Private target Measurement Sets after FLAG processing."
				),
				"stages": ["FLAG"],
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

		if len(overrides) > 128:
			raise ValueError('Too many OXKAT configuration overrides')


		validated = oxkat_scientific_config.validate(
			overrides,
			stage
		)

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
		if (
			isinstance(job_options, dict)
			and job_options.get("stage") in ("1GC", "FLAG")
		):
			self.validation_status = (
				"OXKAT 1GC and FLAG are supported only through "
				"V2 pipeline submission. These stages require "
				"authorized dataset or retained-artifact bindings."
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

