"""Database-backed datasets and team authorization for CAESAR-REST.

All methods operate on Flask-PyMongo's existing database.  No API paths are
returned to regular users. Identifiers and membership are administrator-managed.
"""
import os
import re
from datetime import datetime, timezone
from flask import current_app, g
from caesar_rest import mongo

ID_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$')


class DatasetError(Exception):
	def __init__(self, message, status=400):
		super().__init__(message)
		self.status = status


def database():
	if not current_app.config.get('DATASET_REGISTRY_ENABLED', False):
		raise DatasetError('Dataset registry disabled', 503)
	if not current_app.config.get('USE_MONGO', False) or mongo is None or mongo.db is None:
		raise DatasetError('Dataset registry requires MongoDB', 503)
	return mongo.db


def identity():
	"""Return stable (issuer, sub) identity; anonymous mode cannot access registry."""
	claims = getattr(g, 'oidc_token_info', None)
	if not current_app.config.get('USE_AAI', False) or not isinstance(claims, dict):
		raise DatasetError('Authentication required for dataset access', 401)
	issuer, subject = claims.get('iss'), claims.get('sub')
	if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
		raise DatasetError('OIDC issuer and subject required', 401)
	return issuer + '|' + subject

def sync_current_user():
	"""
	Synchronize user metadata from validated OIDC claims.

	Authorization continues to use issuer|subject.
	Usernames and emails are display metadata only.
	"""

	user_id = identity()
	claims = g.oidc_token_info

	username = claims.get('preferred_username')
	email = claims.get('email')
	name = claims.get('name')

	if not isinstance(username, str) or not username.strip():
		username = None
	else:
		username = username.strip()

	if not isinstance(email, str) or not email.strip():
		email = None
	else:
		email = email.strip()

	if not isinstance(name, str) or not name.strip():
		name = None
	else:
		name = name.strip()

	now = datetime.now(timezone.utc)

	ensure_indexes()

	database().users.update_one(
		{'user_id': user_id},
		{
			'$set': {
				'username': username,
				'email': email,
				'name': name,
				'last_seen': now
			},
			'$setOnInsert': {
				'user_id': user_id,
				'created_at': now
			}
		},
		upsert=True
	)

	return user_id

def is_admin(user_id=None):
	user_id = user_id or identity()
	return user_id in current_app.config.get('DATASET_ADMIN_IDENTITIES', [])


def require_admin():
	if not is_admin():
		raise DatasetError('Administrator permission required', 403)


def checked_id(value, label='identifier'):
	if not isinstance(value, str) or not ID_RE.fullmatch(value):
		raise DatasetError('Invalid ' + label)
	return value

def checked_user_id(user_id):
	"""Validate the stable OIDC issuer|subject identifier."""

	if not isinstance(user_id, str):
		raise DatasetError('Member user_id must be issuer|subject')

	if user_id.count('|') != 1:
		raise DatasetError('Member user_id must contain exactly one separator')

	issuer, subject = user_id.split('|', 1)

	if not issuer or not subject:
		raise DatasetError('Member issuer and subject are required')

	if issuer != issuer.strip() or subject != subject.strip():
		raise DatasetError('Invalid whitespace in member user_id')

	return user_id
    

def ensure_indexes():
	db = database()

	db.datasets.create_index('dataset_id', unique=True)
	db.teams.create_index('team_id', unique=True)

	db.team_memberships.create_index(
		[('team_id', 1), ('user_id', 1)],
		unique=True
	)
	db.team_memberships.create_index('user_id')

	db.users.create_index('user_id', unique=True)
    

def validated_path(path, check_exists=True):
	if not isinstance(path, str) or not os.path.isabs(path):
		raise DatasetError('Absolute storage path required')
	resolved = os.path.realpath(path)
	roots = current_app.config.get('DATASET_ALLOWED_ROOTS', [])
	if not roots:
		raise DatasetError('No allowed dataset storage roots configured', 503)
	if not any(os.path.commonpath([resolved, os.path.realpath(root)]) == os.path.realpath(root)
			for root in roots if os.path.isabs(root)):
		raise DatasetError('Dataset path lies outside permitted storage roots', 403)
	if check_exists and not os.path.exists(resolved):
		raise DatasetError('Dataset path does not exist', 400)
	return resolved


def access_allowed(dataset, user_id=None):
	user_id = user_id or identity()
	if not dataset.get('enabled', True):
		return False
	if is_admin(user_id):
		return True
	visibility = dataset.get('visibility', 'admin')
	if visibility == 'public':
		return True
	if visibility != 'restricted':
		return False
	teams = dataset.get('allowed_teams', [])
	if not teams:
		return False
	return database().team_memberships.find_one({'user_id': user_id, 'team_id': {'$in': teams}}, {'_id': 1}) is not None


def get_dataset(dataset_id, user_id=None):
	checked_id(dataset_id, 'dataset ID')
	doc = database().datasets.find_one({'dataset_id': dataset_id})
	if doc is None or not access_allowed(doc, user_id):
		raise DatasetError('Dataset not found or not accessible', 404)
	return doc


def resolve_dataset(dataset_id):
	"""Always recheck both access and actual physical path at submission time."""
	doc = get_dataset(dataset_id)
	path = validated_path(doc['path'])
	if doc.get('type') == 'directory' and not os.path.isdir(path):
		raise DatasetError('Dataset directory is unavailable', 409)
	if doc.get('type') == 'file' and not os.path.isfile(path):
		raise DatasetError('Dataset file is unavailable', 409)
	return path


def guard_abspath(path):
	"""Prevent abspath bypass when registry security is active.

	Conservatively block ALL paths within managed roots. Legitimate data there
	must be accessed via an authorized dataset ID.
	"""
	if not current_app.config.get('DATASET_REGISTRY_ENABLED', False):
		return
	if not isinstance(path, str) or not os.path.isabs(path):
		raise DatasetError('Absolute path required')
	p = os.path.realpath(path)
	for root in current_app.config.get('DATASET_ALLOWED_ROOTS', []):
		if os.path.isabs(root) and os.path.commonpath([p, os.path.realpath(root)]) == os.path.realpath(root):
			raise DatasetError('Use dataset ID for paths within managed dataset roots', 403)


def public_metadata(doc):
	return {k: v for k, v in doc.items() if k in ('name', 'description', 'type', 'format', 'visibility')}

def list_datasets():
	user_id = identity()
	return {d['dataset_id']: public_metadata(d) for d in database().datasets.find({'enabled': True}) if access_allowed(d, user_id)}


def register_dataset(payload):
	""" Register a dataset"""
	
	require_admin()
	if not isinstance(payload, dict):
		raise DatasetError('JSON object required')
	
	allowed = {
		'dataset_id', 'name', 'description', 'path',
		'type', 'format', 'visibility',
		'allowed_teams', 'enabled'
	}

	if set(payload) - allowed:
		raise DatasetError('Unknown registration fields')
		
	dataset_id = checked_id(payload.get('dataset_id'), 'dataset ID')
	name = payload.get('name')
	if not isinstance(name, str) or not name.strip():
		raise DatasetError('Dataset name required')
	
	kind = payload.get('type', 'directory')
	if kind not in ('file', 'directory'):
		raise DatasetError('Invalid dataset type')
	
	visibility = payload.get('visibility', 'admin')
	if visibility not in ('public', 'restricted', 'admin'):
		raise DatasetError('Invalid visibility')
	
	teams = payload.get('allowed_teams', [])
	if not isinstance(teams, list) or len(teams) != len(set(str(v) for v in teams)):
		raise DatasetError('Invalid allowed_teams')
	
	for team in teams:
		checked_id(team, 'team ID')
		if database().teams.find_one({'team_id': team, 'enabled': True}) is None:
			raise DatasetError('Unknown or disabled team: ' + team)
	
	path = validated_path(payload.get('path'))
	if (kind == 'directory' and not os.path.isdir(path)) or (kind == 'file' and not os.path.isfile(path)):
		raise DatasetError('Dataset path type mismatch')
	
	doc = {'dataset_id': dataset_id, 'name': name.strip(), 'path': path,
		'type': kind, 'visibility': visibility, 'allowed_teams': teams,
		'enabled': payload.get('enabled', True), 'created_by': identity(),
		'created_at': datetime.now(timezone.utc)}
	
	if not isinstance(doc['enabled'], bool):
		raise DatasetError('enabled must be boolean')
	
	for k in ('description', 'format'):
		v = payload.get(k, '')
		if not isinstance(v, str):
			raise DatasetError(k + ' must be text')
		doc[k] = v
	
	from pymongo.errors import DuplicateKeyError
	try:
		ensure_indexes()
		database().datasets.insert_one(doc)
	except DuplicateKeyError:
		raise DatasetError('Dataset ID already registered', 409)
	
	return doc


def update_dataset(dataset_id, payload):
	""" Update dataset """
	
	require_admin()
	checked_id(dataset_id, 'dataset ID')
	if not isinstance(payload, dict) or not payload:
		raise DatasetError('Nonempty JSON object required')
	
	allowed = {
		'name', 'description', 'format',
		'enabled', 'visibility', 'allowed_teams'
	}

	if set(payload) - allowed:
		raise DatasetError('Immutable or unknown dataset field')
		
	if 'name' in payload and (not isinstance(payload['name'], str) or not payload['name'].strip()):
		raise DatasetError('Invalid name')
	
	for k in ('description', 'format'):
		if k in payload and not isinstance(payload[k], str):
			raise DatasetError(k + ' must be text')
	
	if 'enabled' in payload and not isinstance(payload['enabled'], bool):
		raise DatasetError('enabled must be boolean')
	
	if 'visibility' in payload and payload['visibility'] not in ('public', 'restricted', 'admin'):
		raise DatasetError('Invalid visibility')
	
	if 'allowed_teams' in payload:
		teams = payload['allowed_teams']
		if not isinstance(teams, list) or len(teams) != len(set(map(str, teams))):
			raise DatasetError('Invalid allowed_teams')
		for team in teams:
			checked_id(team, 'team ID')
			if database().teams.find_one({'team_id': team, 'enabled': True}) is None:
				raise DatasetError('Unknown or disabled team: ' + team)
	
	res = database().datasets.update_one({'dataset_id': dataset_id}, {'$set': payload})
	if not res.matched_count:
		raise DatasetError('Dataset not found', 404)


def unregister_dataset(dataset_id):
	""" Unregister dataset """
	
	require_admin()
	checked_id(dataset_id, 'dataset ID')
	# Disable/unregister only; never delete files. Check running jobs separately before deployment.
	res = database().datasets.update_one({'dataset_id': dataset_id}, {'$set': {'enabled': False}})
	if not res.matched_count:
		raise DatasetError('Dataset not found', 404)


def create_team(payload):
	require_admin()
	if not isinstance(payload, dict) or set(payload) - {'team_id', 'name', 'description'}:
		raise DatasetError('Invalid team payload')
	team_id = checked_id(payload.get('team_id'), 'team ID')
	name = payload.get('name')
	if not isinstance(name, str) or not name.strip():
		raise DatasetError('Team name required')
	from pymongo.errors import DuplicateKeyError
	ensure_indexes()
	try:
		database().teams.insert_one({'team_id': team_id, 'name': name.strip(),
			'description': payload.get('description', ''), 'enabled': True})
	except DuplicateKeyError:
		raise DatasetError('Team already exists', 409)


def add_member(team_id, user_id):
	"""Add an OIDC user identity to a team."""

	require_admin()
	checked_id(team_id, 'team ID')
	checked_user_id(user_id)

	if database().teams.find_one({
		'team_id': team_id,
		'enabled': True
	}) is None:
		raise DatasetError('Team not found', 404)

	ensure_indexes()

	database().team_memberships.update_one(
		{
			'team_id': team_id,
			'user_id': user_id
		},
		{
			'$setOnInsert': {
				'team_id': team_id,
				'user_id': user_id
			}
		},
		upsert=True
	)

def remove_member(team_id, user_id):
	"""Remove an OIDC user identity from a team."""

	require_admin()
	checked_id(team_id, 'team ID')
	checked_user_id(user_id)

	db = database()

	query = {
		'team_id': team_id,
		'user_id': user_id
	}

	# Diagnostic: check the exact matching document.
	matching_member = db.team_memberships.find_one(query)

	# Diagnostic: inspect the stored IDs for this team.
	stored_members = list(
		db.team_memberships.find(
			{'team_id': team_id},
			{'_id': 0, 'user_id': 1}
		)
	)

	print("DELETE QUERY:", repr(query))
	print("MATCHING MEMBER:", repr(matching_member))
	print("STORED MEMBERS:", repr(stored_members))

	result = db.team_memberships.delete_one(query)

	print("DELETED COUNT:", result.deleted_count, flush=True)

	return result.deleted_count > 0


def list_team_members(team_id):
	"""Return team members enriched with cached user metadata."""

	require_admin()
	checked_id(team_id, 'team ID')

	db = database()

	if db.teams.find_one({'team_id': team_id}) is None:
		raise DatasetError('Team not found', 404)

	memberships = list(
		db.team_memberships.find(
			{'team_id': team_id},
			{'_id': 0, 'user_id': 1}
		)
	)

	user_ids = [m['user_id'] for m in memberships]

	users = {
		user['user_id']: user
		for user in db.users.find(
			{'user_id': {'$in': user_ids}},
			{
				'_id': 0,
				'user_id': 1,
				'username': 1,
				'email': 1,
				'name': 1
			}
		)
	}

	result = []

	for membership in memberships:
		user_id = membership['user_id']
		user = users.get(user_id, {})

		result.append({
			'user_id': user_id,
			'username': user.get('username'),
			'email': user.get('email'),
			'name': user.get('name')
		})

	return sorted(
		result,
		key=lambda member: (
			member['username'] or '',
			member['user_id']
		)
	)

def resolve_input_dataset(dataset_id):
	"""Resolve DB dataset, falling back only for admins to legacy static entries."""
	if not current_app.config.get('DATASET_REGISTRY_ENABLED', False):
		entry = current_app.config.get('DATASETS', {}).get(dataset_id)
		if not entry or not entry.get('path'):
			raise DatasetError('Dataset not found', 404)
		return entry['path']
	checked_id(dataset_id, 'dataset ID')
	if database().datasets.find_one({'dataset_id': dataset_id}) is not None:
		return resolve_dataset(dataset_id)
	# Migration policy: old static configuration is not automatically public.
	if is_admin():
		entry = current_app.config.get('DATASETS', {}).get(dataset_id)
		if entry and entry.get('path'):
			return validated_path(entry['path'])
	raise DatasetError('Dataset not found or not accessible', 404)


def available_datasets():
	if not current_app.config.get('DATASET_REGISTRY_ENABLED', False):
		return {k: {field: value for field, value in data.items() if field != 'path'}
			for k, data in current_app.config.get('DATASETS', {}).items() if data.get('path')}
	result = list_datasets()
	if is_admin():
		for k, data in current_app.config.get('DATASETS', {}).items():
			if k not in result and data.get('path'):
				result[k] = {field: value for field, value in data.items() if field != 'path'}
	return result
