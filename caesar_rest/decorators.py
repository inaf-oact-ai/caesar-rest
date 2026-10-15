##############################
#   MODULE IMPORTS
##############################
from functools import wraps
from flask import current_app, request, g
from caesar_rest import oidc
import json

# Get logger
from caesar_rest import logger

def custom_require_login(view_func, scopes_required=None, render_errors=True):
	""" Decorator to require login only if AAI is enabled """
	@wraps(view_func)
	def decorated(*args, **kwargs):
		aai_enabled= current_app.config['USE_AAI']
		has_oidc= (oidc is not None)
		token = None
		if 'Authorization' in request.headers and request.headers['Authorization'].startswith('Bearer '):
			token = request.headers['Authorization'].split(None,1)[1].strip()
		if 'access_token' in request.form:
			token = request.form['access_token']
		elif 'access_token' in request.args:
			token = request.args['access_token']

		validity = oidc.validate_token(token, scopes_required) # no scopes required
		if (validity is True) or (not aai_enabled or not has_oidc):
			return view_func(*args, **kwargs)
		else:
			response_body = {'error': 'invalid_token',
                                     'error_description': validity}
			if render_errors:
				response_body = json.dumps(response_body)
			return response_body, 401, {'WWW-Authenticate': 'Bearer'}
	return decorated
	
	
def custom_require_browser_login(view_func):
	"""Require interactive OIDC login only when AAI is enabled."""

	@wraps(view_func)
	def decorated(*args, **kwargs):

		aai_enabled = current_app.config['USE_AAI']
		has_oidc = (oidc is not None)

		if not aai_enabled:
			return view_func(*args, **kwargs)

		if not has_oidc:
			logger.error("AAI is enabled but OIDC is unavailable")
			return "OIDC authentication is unavailable", 503

		return oidc.require_login(view_func)(*args, **kwargs)

	return decorated

