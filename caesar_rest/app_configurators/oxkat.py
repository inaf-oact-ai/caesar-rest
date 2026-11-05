
"""CAESAR-REST configurator for the OXKAT Measurement Set pipeline.

Implemented Pipeline V2 stages:
- GET_INFO: inspect a registered MeerKAT Measurement Set and produce
  observation, field and calibrator metadata.
- 1GC: perform first-generation calibration and produce derived,
  target-specific Measurement Sets and calibration diagnostics.
- FLAG: process one calibrated science target per run, performing
  flagging, initial imaging and mask generation.
- 2GC: process one flagged science target per run, performing
  second-generation calibration and associated imaging.

3GC_PEEL and 3GC_FACET are reserved but not implemented.

Pipeline V2 uses a dataset-bound pipeline and immutable upstream
artifact bindings. GET_INFO and 1GC consume the registered original
Measurement Set according to stage policy; FLAG and 2GC consume
retained target-specific upstream artifacts.

Scientific target discovery, readiness and bulk planning are
provided through the Pipeline V2 APIs. Bulk registration creates
independent runs but does not submit or execute them.

MAASAI or another external client controls experiment selection,
run submission, scientific evaluation and pipeline progression.

Original datasets and retained upstream artifacts are not modified.
Stages requiring writable Measurement Sets operate on private copies.
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
IMPLEMENTED_STAGES = {"GET_INFO", "1GC", "FLAG", "2GC"}

_FIELD_SELECTION = re.compile(r'^(?:auto|[0-9]+(?:,[0-9]+)*)$')
_TARGET_NAME = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$')

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
			"using the OXKAT scientific pipeline. "
			"GET_INFO extracts observation, field and calibrator metadata; "
			"1GC performs first-generation calibration and produces "
			"calibrated target Measurement Sets and diagnostics; "
			"FLAG performs target-specific flagging, initial imaging "
			"and mask generation; 2GC performs second-generation "
			"calibration and associated imaging using retained FLAG "
			"outputs. The application supports dataset-bound Pipeline "
			"V2 workflows, scientific target readiness and per-target "
			"bulk planning and registration. Each target run is "
			"submitted and evaluated independently. Scientific "
			"experiment selection and pipeline progression remain "
			"the responsibility of an external orchestration client."
		)
		
		
		
		self.tool_categories = ["measurement-set"]
		
		self.input_requirements = {
			"supported_formats": ["ms"],
			"expected_data": (
				"OXKAT processes registered MeerKAT Measurement Set "
				"datasets through CAESAR-REST Pipeline V2. "
				"GET_INFO requires the original Measurement Set. "
				"1GC requires the original Measurement Set and "
				"retained GET_INFO project_info metadata. "
				"FLAG requires a retained calibrated target "
				"Measurement Set from 1GC and project_info metadata. "
				"2GC requires a retained flagged target Measurement "
				"Set from FLAG and compatible project_info metadata. "
				"FLAG and 2GC process one science target per run."
			),
			"notes": [
				"Create a Pipeline V2 instance with app='oxkat' "
				"and the accessible dataset_id in the pipeline "
				"creation payload.",
				"Do not repeat dataset_id in run registrations "
				"for a dataset-bound pipeline.",
				"Measurement Sets are registered server-side; "
				"large scientific datasets are not uploaded.",
				"GET_INFO reads the original registered Measurement "
				"Set without modifying it.",
				"1GC consumes the original Measurement Set and "
				"retained project_info from GET_INFO.",
				"1GC produces derived target Measurement Sets "
				"and calibration diagnostics in a private workspace.",
				"FLAG consumes retained target_ms from 1GC and "
				"compatible project_info metadata.",
				"2GC consumes retained target_ms from FLAG and "
				"compatible project_info metadata.",
				"FLAG and 2GC support the target parameter to "
				"identify the science target being processed.",
				"FLAG and 2GC require private writable copies "
				"of their input target Measurement Sets.",
				"Scientific target readiness and bulk planning "
				"are available through Pipeline V2 endpoints.",
				"Bulk planning proposes eligible target runs; "
				"bulk registration creates runs without submitting "
				"them for execution.",
				"Individual run registration supports alternative "
				"scientific configurations through oxkat_config.",
				"Clients must use server-resolved dataset identities "
				"and upstream artifact references, not filesystem "
				"paths or arbitrary artifact indices.",
				"Upstream runs must have suitable completed and "
				"retained outputs before downstream binding."
			]
		}

		
		self.limitations = [
			"GET_INFO, 1GC, FLAG and 2GC are supported through "
			"Pipeline V2; 3GC_PEEL and 3GC_FACET are not implemented.",
			"1GC requires the original registered Measurement Set "
			"and retained project_info from GET_INFO.",
			"FLAG requires a retained calibrated target Measurement "
			"Set from 1GC and compatible project_info metadata.",
			"2GC requires a retained flagged target Measurement Set "
			"from FLAG and compatible project_info metadata.",
			"FLAG and 2GC process one science target per run.",
			"Derived Measurement Sets are processed using private "
			"writable copies; original datasets and retained "
			"upstream artifacts must remain unchanged.",
			"Scientific target discovery and planning depend on "
			"available dataset inspection metadata and selected "
			"upstream results.",
			"Bulk registration creates independent pipeline runs "
			"but does not submit or execute them.",
			"No automatic scientific quality assessment, "
			"experiment optimization or downstream stage "
			"advancement is performed by CAESAR-REST.",
			"Run completion alone does not guarantee that "
			"outputs are retained and consumable.",
			"Registered directory artifacts cannot be downloaded "
			"through the regular-file artifact endpoint."
		]


		
		# - Set valid options
		self.valid_options = {
			"stage": EnumValueOption(
				name="stage",
				value="",
				value_type=str,
				description=(
					"OXKAT scientific processing stage. "
					"GET_INFO extracts observation metadata; "
					"1GC performs first-generation calibration "
					"and produces calibrated target Measurement Sets; "
					"FLAG performs target-specific flagging, initial "
					"imaging and mask generation using retained "
					"1GC products; 2GC performs second-generation "
					"calibration and imaging using retained FLAG "
					"products. 3GC_PEEL and 3GC_FACET are reserved "
					"but not implemented. FLAG and 2GC support "
					"one explicitly selected science target per run."
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
					"Generated first-generation calibration execution "
					"script used by the OXKAT 1GC workflow."
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
				"stages": ["1GC","FLAG","2GC"],
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
			"gc2_execution_script": {
				"path": "submit_2GC_jobs.sh",
				"glob": None,
				"type": "text/x-shellscript",
				"role": "diagnostic",
				"description": "Generated OXKAT 2GC execution script.",
				"stages": ["2GC"],
				"required": False,
			},
			"gc2_images": {
				"path": "IMAGES",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "primary_result",
				"description": "2GC imaging, beam correction and mask products.",
				"stages": ["2GC"],
				"required": False,
			},
			"gc2_target_measurement_sets": {
				"path": None,
				"glob": "*.ms",
				"kind": "directory",
				"type": "application/x-casa-measurement-set",
				"role": "primary_result",
				"description": "Target Measurement Sets after 2GC self-calibration.",
				"stages": ["2GC"],
				"required": False,
			},
			"gc2_gain_tables": {
				"path": "GAINTABLES",
				"glob": None,
				"kind": "directory",
				"type": "application/octet-stream",
				"role": "primary_result",
				"description": "Second-generation CubiCal calibration solutions.",
				"stages": ["2GC"],
				"required": False,
			},
			"image_qa": {
				"path": "previews/image_qa.json",
				"glob": None,
				"type": "application/json",
				"role": "diagnostic",
				"description": (
					"Complete OXKAT imaging QA, preview index, "
					"imaging families and BANE/Aegean statistics."
				),
				"format": "",
				"parser": "json",
				"stages": ["FLAG", "2GC"],
				"required": False,
			},
			"image_previews": {
				"path": None,
				"glob": "previews/selected/preview_*.png",
				"type": "image/png",
				"role": "diagnostic",
				"description": (
					"Curated imaging previews across OXKAT "
					"imaging families."
				),
				"format": "png",
				"parser": "",
				"stages": ["FLAG", "2GC"],
				"required": False,
			},
			"sourcefind_logs": {
				"path": None,
				"glob": "previews/logs/sourcefind_*.log",
				"type": "text/plain",
				"role": "diagnostic",
				"description": "BANE and Aegean execution logs.",
				"stages": ["FLAG", "2GC"],
				"required": False,
			},
			"sourcefind_catalog_native": {
				"path": None,
				"glob": "previews/catalog/sourcefind_*.dat",
				"type": "text/plain",
				"role": "diagnostic",
				"description": "Aegean native ASCII catalogs.",
				"stages": ["FLAG", "2GC"],
				"required": False,
			},
			"sourcefind_catalog_tables": {
				"path": None,
				"glob": "previews/catalog/sourcefind_*.tab",
				"type": "text/tab-separated-values",
				"role": "diagnostic",
				"description": (
					"Aegean component and island source tables."
				),
				"stages": ["FLAG", "2GC"],
				"required": False,
			},
			"sourcefind_catalog_regions": {
				"path": None,
				"glob": "previews/catalog/sourcefind_*.reg",
				"type": "text/plain",
				"role": "diagnostic",
				"description": (
					"Aegean component and island DS9 regions."
				),
				"stages": ["FLAG", "2GC"],
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

		unknown = set(job_options) - {'stage', 'target', 'oxkat_config'}

		if unknown:
			raise ValueError(
				'Unsupported OXKAT job options: %s' %
				', '.join(sorted(unknown))
			)
			
		if 'target' in job_options:
			target = job_options['target']

			if stage not in ('FLAG', '2GC'):
				raise ValueError(
					'target is supported only for FLAG and 2GC'
				)

			if (
				not isinstance(target, str)
				or not _TARGET_NAME.fullmatch(target)
			):
				raise ValueError('Invalid OXKAT target name')			
			
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

		scalar_parameters = dict(parameters)
		scalar_parameters.pop('oxkat_config', None)
		target = scalar_parameters.pop('target', None)

		args = scalar_validator(scalar_parameters, allowed)

		if target is not None:
			args.append('--target-name=%s' % target)

		if overrides is not None:
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


	def build_scientific_readiness(self, pipeline, runs, dataset_doc):
		"""Evaluate OXKAT readiness using persisted scientific metadata."""

		from caesar_rest.app_configurators import oxkat_readiness

		return oxkat_readiness.resolve_snapshot(
			pipeline,
			runs,
			dataset_doc
		)

	def build_bulk_plan(self, scientific, stage, targets=None):
		"""Translate scientific readiness into OXKAT run proposals."""

		from caesar_rest.app_configurators import oxkat_readiness

		return oxkat_readiness.build_bulk_plan(
			scientific,
			stage,
			targets
		)

	def validate_pipeline_bindings(self, parameters, bindings):
		"""Validate target-specific OXKAT V2 artifact bindings.

		FLAG and 2GC must consume the Measurement Set corresponding
		to the explicitly requested science target.

		The binding metadata comes from owner-scoped pipeline records,
		not from client-supplied filesystem paths.
		"""

		if not isinstance(parameters, dict):
			raise ValueError('Invalid OXKAT pipeline parameters')

		if not isinstance(bindings, dict):
			raise ValueError('Invalid OXKAT pipeline bindings')

		stage = parameters.get('stage')

		if stage not in ('FLAG', '2GC'):
			return None

		target = parameters.get('target')

		# Preserve backward compatibility with existing single-target
		# runs that do not specify an explicit target.
		if target is None:
			return None

		if (
			not isinstance(target, str)
			or not _TARGET_NAME.fullmatch(target)
		):
			raise ValueError('Invalid OXKAT target name')

		target_binding = bindings.get('target_ms')
		project_binding = bindings.get('project_info')

		if not isinstance(target_binding, dict):
			raise ValueError(
				'OXKAT requires a retained target_ms artifact'
			)

		if not isinstance(project_binding, dict):
			raise ValueError(
				'OXKAT requires a retained project_info artifact'
			)

		if target_binding.get('artifact_kind') != 'directory':
			raise ValueError(
				'OXKAT target_ms must be a directory artifact'
			)

		if target_binding.get('source_stage') not in (
			'1GC',
			'FLAG'
		):
			raise ValueError(
				'OXKAT target_ms comes from an unsupported stage'
			)

		if (
			stage == 'FLAG'
			and target_binding.get('source_stage') != '1GC'
		):
			raise ValueError(
				'FLAG target_ms must originate from 1GC'
			)

		if (
			stage == '2GC'
			and target_binding.get('source_stage') != 'FLAG'
		):
			raise ValueError(
				'2GC target_ms must originate from FLAG'
			)

		expected_artifact_names = {
			'1GC': 'working_measurement_sets',
			'FLAG': 'flagged_target_measurement_sets'
		}

		source_stage = target_binding['source_stage']

		if target_binding.get('artifact_name') != (
			expected_artifact_names[source_stage]
		):
			raise ValueError(
				'Unexpected OXKAT target Measurement Set artifact'
			)

		relative_path = target_binding.get('relative_path')

		if not isinstance(relative_path, str):
			raise ValueError(
				'Invalid OXKAT target artifact path'
			)

		ms_name = relative_path.rsplit('/', 1)[-1]

		if not ms_name.endswith('_' + target + '.ms'):
			raise ValueError(
				'Selected Measurement Set does not match '
				'the requested OXKAT target: %s' % target
			)

		if (
			project_binding.get('artifact_name') != 'project_info'
			or project_binding.get('artifact_kind') != 'file'
		):
			raise ValueError(
				'Invalid OXKAT project_info binding'
			)

		if stage == 'FLAG':
			if project_binding.get('source_stage') not in (
				'GET_INFO',
				'1GC'
			):
				raise ValueError(
					'FLAG project_info must originate from '
					'GET_INFO or 1GC'
				)

		if stage == '2GC':
			if project_binding.get('source_stage') not in (
				'GET_INFO',
				'1GC',
				'FLAG'
			):
				raise ValueError(
					'2GC project_info comes from an unsupported stage'
				)
				
			if project_binding.get('source_stage') == 'FLAG':
				if (
					project_binding.get('source_run_id')
					!= target_binding.get('source_run_id')
				):
					raise ValueError(
						'2GC project_info and target_ms must originate '
						'from the same FLAG run'
					)				

		return None


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
			and job_options.get("stage") in ("1GC", "FLAG", "2GC")
		):
			self.validation_status = (
				"OXKAT 1GC, FLAG and 2GC are supported only through "
				"V2 pipeline submission."
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

