
"""Idempotency primitives for Pipeline V2 registration.

The authoritative uniqueness guarantee is a MongoDB unique partial index
on (owner, pipeline_id, idempotency_key).

These helpers perform request identity validation and replay lookup.
They do not register runs, submit jobs or mutate database records.
"""

import hashlib
import json
import re

from caesar_rest.pipeline import manager


_KEY_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')


def validate_key(value):
	"""Validate a client-generated registration idempotency key."""

	if (
		not isinstance(value, str)
		or _KEY_RE.fullmatch(value) is None
	):
		raise manager.PipelineError(
			'idempotency_key must be 1-128 ASCII characters '
			'using letters, digits, underscores, dots, colons '
			'or hyphens',
			400
		)

	return value


def fingerprint(payload):
	"""Return a deterministic SHA-256 digest of a registration request.

	Dictionary key ordering does not affect the digest.
	List ordering remains significant.
	"""

	if not isinstance(payload, dict):
		raise manager.PipelineError(
			'Registration payload must be a JSON object',
			400
		)

	try:
		serialized = json.dumps(
			payload,
			sort_keys=True,
			separators=(',', ':'),
			ensure_ascii=True,
			allow_nan=False
		)
	except (TypeError, ValueError, OverflowError) as exc:
		raise manager.PipelineError(
			'Registration payload is not valid JSON',
			400
		) from exc

	return hashlib.sha256(
		serialized.encode('utf-8')
	).hexdigest()


def find_existing(
	runs_collection,
	owner,
	pipeline_id,
	key,
	request_fingerprint
):
	"""Return a prior matching registration, or None.

	The lookup is scoped to the authenticated owner and pipeline.
	A reused key with a different payload is a conflict.
	"""

	validate_key(key)

	if (
		not isinstance(request_fingerprint, str)
		or re.fullmatch(r'[0-9a-f]{64}', request_fingerprint) is None
	):
		raise manager.PipelineError(
			'Invalid request fingerprint',
			400
		)

	doc = runs_collection.find_one({
		'owner': owner,
		'pipeline_id': pipeline_id,
		'idempotency_key': key
	})

	if doc is None:
		return None

	if doc.get('request_fingerprint') != request_fingerprint:
		raise manager.PipelineError(
			'Idempotency key was already used with '
			'a different registration request',
			409
		)

	return manager.public_doc(doc)

