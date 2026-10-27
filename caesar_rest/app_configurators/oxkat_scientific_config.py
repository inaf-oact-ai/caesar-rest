"""Versioned allowlist of OXKAT scientific configuration values.

Copy the same reviewed file into CAESAR-REST and oxkat-caesar. Only values in
SCHEMA can be changed; paths, execution controls and infrastructure are absent.
"""
import ast
import json
import math
import re

SCHEMA_VERSION = 1
STAGES = ('GET_INFO', '1GC', 'FLAG', '2GC', '3GC_PEEL', '3GC_FACET')
SCHEMA = {}


def add(names, kind, stages, **constraints):
	for name in names.split():
		if name in SCHEMA:
			raise ValueError('Repeated schema name: ' + name)
		SCHEMA[name] = dict(kind=kind, stages=tuple(stages.split()), **constraints)


# GET_INFO and 1GC selection and pre-processing.
add('CAL_1GC_TARGET_INTENT CAL_1GC_PRIMARY_INTENT CAL_1GC_SECONDARY_INTENT', 'token', 'GET_INFO')
add('PRE_FIELDS PRE_SCANS', 'selection', '1GC')
add('PRE_NCHANS CAL_1GC_FILLGAPS CAL_1GC_LINE_FILLGAPS', 'integer', '1GC', minimum=1, maximum=65536)
add('PRE_TIMEBIN', 'duration', '1GC')
add('CAL_1GC_REF_ANT', 'selection', '1GC')
add('CAL_1GC_REF_POOL', 'antenna_list', '1GC')
add('CAL_1GC_PRIMARY CAL_1GC_TARGETS CAL_1GC_SECONDARIES', 'selection', 'GET_INFO')
add('CAL_1GC_DELAYCUT', 'number', '1GC', minimum=0, maximum=10000)
add('CAL_1GC_FREQRANGE CAL_1GC_UVRANGE CAL_1GC_BL_FLAG_UVRANGE', 'casa_selection', '1GC')
add('CAL_1GC_BAD_FREQS CAL_1GC_BL_FREQS', 'casa_selection_list', '1GC')
# CAL_1GC_0408_MODEL intentionally excluded: compound model needs separate physics validation.
# CAL_1GC_PRIMARY_MODEL intentionally excluded: can name arbitrary filesystem paths.
add('CAL_2GC_UVRANGE', 'casa_selection', '2GC')
add('CAL_2GC_PSOLINT CAL_2GC_APSOLINT', 'duration', '2GC')
add('CAL_3GC_PEEL_NCHAN', 'integer', '3GC_PEEL', minimum=1, maximum=65536)
add('CAL_3GC_PEEL_BRIGGS', 'number', '3GC_PEEL', minimum=-2, maximum=2)
# 3GC region, parset and data column settings can control paths/outputs and are excluded.
add('SAVE_FLAGS', 'boolean', 'FLAG')

# WSClean: science and bounded scientific resource choices.
WSC = 'FLAG 2GC 3GC_PEEL 3GC_FACET'
add('WSC_MEM', 'integer', WSC, minimum=1, maximum=1000)
add('WSC_ABSMEM', 'integer', WSC, minimum=-1, maximum=1000)
add('WSC_CONTINUE WSC_MAKEPSF WSC_NODIRTY WSC_SOURCELIST WSC_EVEN WSC_ODD WSC_USEWGRIDDER WSC_BDA WSC_NOMODEL WSC_USEIDG WSC_MULTISCALE WSC_JOINCHANNELS WSC_NONEGATIVE WSC_STOPNEGATIVE WSC_CIRCULARBEAM WSC_LOCALRMS', 'boolean', WSC)
add('WSC_PARALLELREORDERING WSC_PARALLELDECONVOLUTION', 'integer', WSC, minimum=0, maximum=16384)
add('WSC_FIELD', 'integer', WSC, minimum=0, maximum=10000)
add('WSC_STARTCHAN WSC_ENDCHAN', 'integer', WSC, minimum=-1, maximum=65536)
add('WSC_INTERVAL0 WSC_INTERVAL1 WSC_INTERVALSOUT', 'nullable_integer', WSC, minimum=0, maximum=10000000)
add('WSC_IMSIZE', 'integer', WSC, minimum=64, maximum=65536)
add('WSC_CELLSIZE', 'angular_scale', WSC)
add('WSC_WGRIDDERACCURACY', 'number', WSC, minimum=1e-9, maximum=1)
add('WSC_BDAFACTOR WSC_NWLAYERSFACTOR WSC_PADDING', 'number', WSC, minimum=0.01, maximum=100)
add('WSC_PREDICTCHANNELS WSC_CHANNELSOUT', 'integer', WSC, minimum=1, maximum=65536)
add('WSC_BRIGGS', 'number', WSC, minimum=-2, maximum=2)
add('WSC_MINUVL WSC_MAXUVL WSC_TAPERGAUSSIAN', 'bounded_scientific_string', WSC)
add('WSC_IDGMODE', 'enum', WSC, choices=['CPU', 'GPU', 'Hybrid'])
add('WSC_SCALES', 'scales', WSC)
add('WSC_NITER', 'integer', WSC, minimum=0, maximum=10000000)
add('WSC_GAIN WSC_MGAIN', 'number', WSC, minimum=1e-6, maximum=1)
add('WSC_FITSPECTRALPOL', 'integer', WSC, minimum=0, maximum=20)
add('WSC_MASK', 'mask_mode', WSC)
add('WSC_THRESHOLD', 'number', WSC, minimum=0, maximum=1000000)
add('WSC_AUTOMASK WSC_AUTOTHRESHOLD', 'number', WSC, minimum=0, maximum=10000)

# MakeMask science.
add('MAKEMASK_THRESH', 'number', 'FLAG 2GC', minimum=0, maximum=1000)
add('MAKEMASK_BOXSIZE MAKEMASK_SMALLBOX MAKEMASK_ISLANDSIZE MAKEMASK_DILATION', 'integer', 'FLAG 2GC', minimum=0, maximum=1000000)

# DDFacet scientific controls; exclude columns, directories, mask files and model paths.
DDF = '3GC_PEEL 3GC_FACET'
add('DDF_CHUNKHOURS DDF_DIAMMAX DDF_DIAMMIN DDF_PSFOVERSIZE DDF_PADDING DDF_ROBUST DDF_FITSPARANGLEINCDEG DDF_GAIN DDF_FLUXTHRESHOLD DDF_RMSFACTOR DDF_SSD_DECONVPEAKFACTOR DDF_HOGBOM_DECONVPEAKFACTOR', 'number', DDF, minimum=0, maximum=1000000)
# DDF_ROBUST is a special case with negative weighting allowed.
SCHEMA['DDF_ROBUST']['minimum'] = -2
add('DDF_NPIX DDF_NFACETS DDF_NCPU DDF_BEAMNBAND DDF_DTBEAMMIN DDF_FEEDSWAP DDF_NBAND DDF_NDEGRIDBAND DDF_CYCLEFACTOR DDF_SSD_MAXMAJORITER DDF_SSD_MAXMINORITER DDF_SSD_ENLARGEDATA DDF_HOGBOM_MAXMAJORITER DDF_HOGBOM_MAXMINORITER DDF_HOGBOM_POLYFITORDER DDF_CONSERVEMEMORY', 'integer', DDF, minimum=0, maximum=10000000)
add('DDF_CELL', 'number', DDF, minimum=0.00001, maximum=1000)
add('DDF_BEAMCENTRENORM DDF_BEAMSMOOTH', 'boolean', DDF)
add('DDF_DECONVMODE', 'enum', DDF, choices=['hogbom', 'SSD'])
add('DDF_MASKSIGMA', 'number', DDF, minimum=0, maximum=1000)
# DDF control/outputs/column names are intentionally not exposed by default.

# killMS numerical/scientific controls, excluding data paths, outputs and columns.
add('KMS_TCHUNK KMS_MAXFACETSIZE KMS_COVQ', 'number', DDF, minimum=0, maximum=1000000)
add('KMS_DT KMS_NCHANSOLS KMS_NITERKF KMS_NCPU KMS_NCHANBEAMPERMS KMS_FIELDID KMS_DDID', 'integer', DDF, minimum=0, maximum=10000000)
add('KMS_UVMINMAX', 'pair_numbers', DDF)
add('KMS_SOLVERTYPE', 'enum', DDF, choices=['KAFCA', 'CohJones'])

# Source finding and clustering scientific settings.
add('PYBDSF_THRESH_PIX PYBDSF_THRESH_ISL CLUSTERCAT_CENTRALRADIUS CLUSTERCAT_FLUXMIN', 'number', DDF, minimum=0, maximum=1000000)
add('PYBDSF_CATALOGTYPE', 'enum', DDF, choices=['srl', 'gaul'])
add('PYBDSF_CATALOGFORMAT', 'enum', DDF, choices=['fits', 'ascii'])
add('CLUSTERCAT_NDIR CLUSTERCAT_NGEN CLUSTERCAT_NCPU', 'integer', DDF, minimum=1, maximum=1000000)


def validate(overrides, stage):
	"""Return clean JSON-compatible values; reject unregistered inputs."""
	
	if stage not in STAGES or not isinstance(overrides, dict) or not 0 < len(overrides) <= 128:
		raise ValueError('Invalid stage or OXKAT override object')
	
	clean = {}
	for name, value in overrides.items():
		spec = SCHEMA.get(name)
		
		if spec is None or stage not in spec['stages']:
			raise ValueError('Unsupported OXKAT parameter for stage: %s' % name)
		
		kind = spec['kind']
		if kind == 'boolean':
			valid = type(value) is bool
		
		elif kind in ('integer', 'nullable_integer'):
			valid = type(value) is int or (kind == 'nullable_integer' and value is None)
		
		elif kind == 'number':
			valid = type(value) in (int, float) and math.isfinite(value)
			if valid:
				value = float(value)
		
		elif kind == 'enum':
			valid = type(value) is str and value in spec['choices']
		
		elif kind in ('selection', 'token', 'duration', 'casa_selection', 'bounded_scientific_string', 'angular_scale', 'mask_mode', 'scales', 'pair_numbers'):
			valid = type(value) is str and len(value) <= 256 and '\n' not in value and '\r' not in value and '\x00' not in value
			if valid:
				if kind == 'selection':
					valid = bool(re.fullmatch(r'(?:auto|[A-Za-z0-9_,.-]*)', value))
				elif kind == 'token':
					valid = bool(re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value))
				elif kind == 'duration':
					valid = bool(re.fullmatch(r'(?:inf|[0-9]+(?:\.[0-9]+)?(?:s|m|h)?)', value))
				elif kind == 'angular_scale':
					valid = bool(re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:asec|amin|deg)', value))
				elif kind == 'mask_mode':
					valid = value in ('auto', 'fits', '')
				elif kind == 'scales':
					valid = bool(re.fullmatch(r'[0-9]+(?:,[0-9]+)*', value))
					if valid:
						nums = [int(x) for x in value.split(',')]
						valid = 1 <= len(nums) <= 16 and nums == sorted(set(nums)) and max(nums) <= 16384
				elif kind == 'pair_numbers':
					valid = bool(re.fullmatch(r'[0-9]+(?:\.[0-9]+)?,[0-9]+(?:\.[0-9]+)?', value))
				else:
					# CASA ranges and numeric science strings: no whitespace,
					# path separators, quotes or shell metacharacters.
					valid = bool(re.fullmatch(r'[A-Za-z0-9_.,:~*+<>\-]*', value))
		
		elif kind == 'antenna_list':
			valid = isinstance(value, list) and 1 <= len(value) <= 64 and all(
				isinstance(x, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,24}', x) for x in value)
		
		elif kind == 'casa_selection_list':
			valid = isinstance(value, list) and len(value) <= 128 and all(
				isinstance(x, str) and len(x) <= 256 and
				re.fullmatch(r'[A-Za-z0-9_.,:~*+<>\-]*', x) for x in value)
		
		else:
			raise ValueError('Invalid registry kind')
		
		if not valid:
			raise ValueError('Invalid OXKAT parameter value: %s' % name)
		
		if value is not None and type(value) in (int, float):
			if not spec.get('minimum', -float('inf')) <= value <= spec.get('maximum', float('inf')):
				raise ValueError('Out-of-range OXKAT parameter: %s' % name)
		
		clean[name] = value
	
	return clean


def append_overrides(config_path, overrides, stage):
	"""Append safe, validated Python assignments AFTER upstream band modifiers.

	Upstream config.py is trusted, container-packaged code. Values originate
	only from validated primitive JSON and cannot create Python statements.
	"""
	values = validate(overrides, stage)
	with open(config_path, encoding='utf-8') as stream:
		source = stream.read()
	tree = ast.parse(source)
	assignments = {
		target.id for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))
		for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
		if isinstance(target, ast.Name)
	}
	if set(values) - assignments:
		raise ValueError('OXKAT config.py is missing requested parameter(s)')
	with open(config_path, 'a', encoding='utf-8') as stream:
		stream.write('\n# CAESAR-REST validated science overrides (after band modifiers)\n')
		for key, val in sorted(values.items()):
			stream.write('%s = %s\n' % (key, repr(val)))
	return values


def schema_digest():
	import hashlib
	return hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest()
