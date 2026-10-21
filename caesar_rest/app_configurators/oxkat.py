"""CAESAR-REST configurator for the oxkat Measurement Set pipeline.

Initial executable stage: GET_INFO. Additional stages are represented by the
stage selector but are rejected until run_oxkat.sh implements them.

The data input is a *directory* ending in .ms, not an uploaded file. Prefer a
server-configured dataset identifier whose path resolves to shared storage.
"""

import os

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
IMPLEMENTED_STAGES = {"GET_INFO"}


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
			"Process radio-interferometric Measurement Sets with oxkat. "
			"Select the processing stage using the 'stage' option. "
			"The initial release executes GET_INFO to inspect an observation "
			"and determine calibration targets and observation metadata. "
			"Other calibration/imaging stages are reserved for future releases."
		)
		self.tool_categories = ["measurement-set"]
		self.input_requirements = {
			"supported_formats": ["ms"],
			"expected_data": (
				"One MeerKAT Measurement Set directory (*.ms) on a filesystem "
				"available to the scientific execution environment."
			),
			"notes": [
				"Prefer data_inputs.format='dataset' for large Measurement Sets.",
				"Register each Measurement Set path on the server; data is not uploaded.",
				"The GET_INFO stage reads the original dataset without copying it.",
			],
		}
		self.limitations = [
			"Only GET_INFO is executable in this initial integration.",
			"Exactly one input Measurement Set is supported per request.",
			"The input must be a directory with a .ms suffix, accessible to Slurm.",
			"Future calibration stages will require writable per-job datasets.",
		]
		self.valid_options = {
			"stage": EnumValueOption(
				name="stage",
				value="",
				value_type=str,
				description=(
					"Oxkat processing stage. Only GET_INFO is currently executable; "
					"other values are reserved for future implementation."
				),
				category="RUN",
				default_value="GET_INFO",
				allowed_values=OXKAT_STAGES,
			),
		}
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
				"description": "Observation, frequency, field and calibrator metadata.",
				"format": "",
				"parser": "json",
				"required": True,
				"notes": "Produced by the GET_INFO stage.",
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

	def set_data_input_option_value(self):
		"""Translate the one resolved dataset path into the runner's MS option."""
		self.cmd_args.append("--input-ms=%s" % self.data_inputs)

	def validate(self, job_options, data_inputs):
		"""Reject unsupported stages and unsafe/multiple input paths."""
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

