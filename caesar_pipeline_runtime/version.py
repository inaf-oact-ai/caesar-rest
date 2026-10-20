"""Version dispatch for trusted worker specifications.

An omitted version is the legacy v1 contract; malformed values fail closed.
"""


def specification_version(spec, error_type=ValueError):
	if not isinstance(spec, dict):
		raise error_type('Specification must be an object')
	version = spec.get('version', 1)
	if type(version) is not int or version not in (1, 2):
		raise error_type('Unsupported specification version')
	return version
