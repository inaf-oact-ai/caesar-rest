##############################
#   MODULE IMPORTS
##############################
from functools import wraps
from flask import current_app, request, g
from caesar_rest import oidc
import json

# Get logger
from caesar_rest import logger

#def custom_require_login(view_func, scopes_required=None, render_errors=True):
#	""" Decorator to require login only if AAI is enabled """
#	@wraps(view_func)
#	def decorated(*args, **kwargs):
#		aai_enabled= current_app.config['USE_AAI']
#		has_oidc= (oidc is not None)
#		token = None
#		if 'Authorization' in request.headers and request.headers['Authorization'].startswith('Bearer '):
#			token = request.headers['Authorization'].split(None,1)[1].strip()
#		if 'access_token' in request.form:
#			token = request.form['access_token']
#		elif 'access_token' in request.args:
#			token = request.args['access_token']
#
#		validity = oidc.validate_token(token, scopes_required) # no scopes required
#		if (validity is True) or (not aai_enabled or not has_oidc):
#			return view_func(*args, **kwargs)
#		else:
#			response_body = {'error': 'invalid_token',
#                                     'error_description': validity}
#			if render_errors:
#				response_body = json.dumps(response_body)
#			return response_body, 401, {'WWW-Authenticate': 'Bearer'}
#	return decorated
	
	
def custom_require_login(view_func, scopes_required=None, render_errors=True):
    """
    Require a valid OIDC bearer token when AAI is enabled.

    When AAI is disabled, preserve legacy anonymous access.

    With AAI enabled:
      - An available OIDC validator is mandatory.
      - A valid bearer token is mandatory.
      - Validated token claims must be request-local.
      - Invalid tokens never authorize access.
    """

    @wraps(view_func)
    def decorated(*args, **kwargs):

        aai_enabled = current_app.config.get('USE_AAI', False)

        # Clear request-local token information before validation.
        g.oidc_token_info = None

        # Preserve legacy behavior when AAI is disabled.
        if not aai_enabled:
            return view_func(*args, **kwargs)

        def auth_error(message):
            response_body = {
                'error': 'invalid_token',
                'error_description': str(message)
            }

            if render_errors:
                response_body = json.dumps(response_body)

            return response_body, 401, {
                'WWW-Authenticate': 'Bearer'
            }

        # Fail closed when authentication is enabled.
        if oidc is None:
            logger.error(
                "AAI is enabled but OIDC validator is unavailable"
            )
            return auth_error('Authentication service unavailable')

        # Extract bearer token.
        token = None

        auth_header = request.headers.get('Authorization', '')

        if auth_header.startswith('Bearer '):
            token = auth_header.split(None, 1)[1].strip()

        # Preserve legacy token input mechanisms.
        if not token:
            token = (
                request.form.get('access_token')
                or request.args.get('access_token')
            )

        if not token:
            return auth_error('Bearer token required')

        # Validate token through the configured OIDC provider.
        try:
            validity = oidc.validate_token(token, scopes_required)
        except Exception:
            logger.exception("OIDC token validation failed")
            return auth_error('Token validation failed')

        if validity is not True:
            return auth_error(validity)

        return view_func(*args, **kwargs)

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

