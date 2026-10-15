##############################
#   MODULE IMPORTS
##############################
from functools import wraps

from flask import current_app, Blueprint, render_template, request, redirect
from caesar_rest import oidc
from caesar_rest.decorators import custom_require_login
from caesar_rest.decorators import custom_require_browser_login

# Get logger
from caesar_rest import logger

##############################
#   CREATE BLUEPRINT
##############################
index_bp = Blueprint('index', __name__)

@index_bp.route('/')
def index():
	#return render_template('index.html')

	aai_enabled= current_app.config['USE_AAI']
	has_oidc= (oidc is not None)
	logger.debug("use_aai? %d has_oidc? %d" % (aai_enabled, has_oidc))

	if aai_enabled and has_oidc:
		if oidc.user_loggedin:
			return render_template('index.html', username=oidc.user_getfield('email'))
			#return 'Welcome {email}'.format(email=oidc.user_getfield('email'))
		else:
			return 'Not logged in, <a href="/login">Log in</a> '
	else:
		return render_template('index.html')


#@index_bp.route('/login')
#@custom_require_login
#def login():
#	aai_enabled= current_app.config['USE_AAI']
#	has_oidc= (oidc is not None)
#	logger.debug("use_aai? %d has_oidc? %d" % (aai_enabled, has_oidc))
#
#	if aai_enabled and has_oidc:
#		user_info = oidc.user_getinfo(['preferred_username', 'email', 'sub', 'name'])
#		# return value is a dictionary with keys the above keywords
#		return redirect("/", code=302) #'Welcome {user_info}'.format(user_info=user_info['name'])
#
#	else:
#		return render_template('index.html')

@index_bp.route('/login')
@custom_require_browser_login
def login():

	aai_enabled = current_app.config['USE_AAI']
	has_oidc = (oidc is not None)
	logger.debug("use_aai? %d has_oidc? %d" % (aai_enabled, has_oidc))

	if aai_enabled and has_oidc:
		user_info = oidc.user_getinfo(['preferred_username', 'email', 'sub', 'name'])
		logger.debug("OIDC login successful")
		return redirect("/", code=302)

	else:
		return render_template('index.html')


@index_bp.route('/logout')
def logout():
	"""Performs local logout by removing the session cookie."""

	aai_enabled= current_app.config['USE_AAI']
	has_oidc= (oidc is not None)
	logger.debug("use_aai? %d has_oidc? %d" % (aai_enabled, has_oidc))

	if aai_enabled and has_oidc:
		oidc.logout()
		return 'Hi, you have been logged out! <a href="/">Return</a>'
	else:
		return 'Bye bye'

