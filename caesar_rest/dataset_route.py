"""Dataset and team API. Admin writes, filtered authenticated reads."""

from flask import Blueprint, jsonify, request
from flask import g, current_app

from caesar_rest import oidc
from caesar_rest.decorators import custom_require_login
from caesar_rest import dataset_registry as registry

registry_bp = Blueprint('dataset_registry', __name__, url_prefix='/caesar/api/v1.0')


###########################################
###    HELPERS
###########################################
def response_error(error):
	return jsonify({'error': str(error)}), error.status


def invoke(func, *args):
	try:
		# The legacy login decorator can allow anonymous mode;
		# the dataset registry always requires authentication.
		registry.identity()

		# Synchronize the authenticated user's display metadata.
		registry.sync_current_user()

		return func(*args)

	except registry.DatasetError as exc:
		return response_error(exc)

###############################################
####    ENDPOINTS
###############################################
@registry_bp.route('/datasets/me', methods=['GET'])
@custom_require_login
def current_identity():
    def action():
        user_id = registry.identity()
        claims = g.oidc_token_info

        return jsonify({
            'issuer': claims['iss'],
            'subject': claims['sub'],
            'user_id': user_id,
            'is_dataset_admin': registry.is_admin(user_id),
            'registry_enabled': current_app.config.get(
                'DATASET_REGISTRY_ENABLED', False
            )
        })

    return invoke(action)

@registry_bp.route('/datasets', methods=['POST'])
@custom_require_login
def register():
	def action():
		doc = registry.register_dataset(request.get_json(silent=True))
		return jsonify({'dataset_id': doc['dataset_id']}), 201
	return invoke(action)


@registry_bp.route('/datasets/<dataset_id>', methods=['GET'])
@custom_require_login
def describe(dataset_id):
	def action():
		doc = registry.get_dataset(dataset_id)
		return jsonify({'dataset_id': dataset_id, **registry.public_metadata(doc)})
	return invoke(action)


@registry_bp.route('/datasets/<dataset_id>', methods=['PATCH'])
@custom_require_login
def update(dataset_id):
	def action():
		registry.update_dataset(dataset_id, request.get_json(silent=True))
		return jsonify({'dataset_id': dataset_id, 'updated': True})
	return invoke(action)


@registry_bp.route('/datasets/<dataset_id>', methods=['DELETE'])
@custom_require_login
def deactivate(dataset_id):
	def action():
		registry.unregister_dataset(dataset_id)
		return jsonify({'dataset_id': dataset_id, 'enabled': False})
	return invoke(action)


@registry_bp.route('/teams', methods=['GET'])
@custom_require_login
def teams():
	def action():
		registry.require_admin()
		return jsonify([{'team_id': d['team_id'], 'name': d['name'], 'enabled': d.get('enabled', True)}
			for d in registry.database().teams.find({})])
	return invoke(action)


@registry_bp.route('/teams', methods=['POST'])
@custom_require_login
def new_team():
	def action():
		payload = request.get_json(silent=True)
		registry.create_team(payload)
		return jsonify({'team_id': payload['team_id']}), 201
	return invoke(action)


@registry_bp.route('/teams/<team_id>/members', methods=['GET'])
@custom_require_login
def members(team_id):

	def action():
		members = registry.list_team_members(team_id)
		return jsonify(members)

	return invoke(action)

@registry_bp.route('/teams/<team_id>/members', methods=['POST'])
@custom_require_login
def add_team_member(team_id):
	def action():
		payload = request.get_json(silent=True)
		if not isinstance(payload, dict):
			raise registry.DatasetError('JSON object required')
		registry.add_member(team_id, payload.get('user_id'))
		return jsonify({'added': True}), 201
	return invoke(action)


@registry_bp.route('/teams/<team_id>/members', methods=['DELETE'])
@custom_require_login
def delete_team_member(team_id):

	def action():
		payload = request.get_json(silent=True)

		if not isinstance(payload, dict):
			raise registry.DatasetError('JSON object required')

		removed = registry.remove_member(
			team_id,
			payload.get('user_id')
		)

		return jsonify({'removed': removed})

	return invoke(action)
