##############################
#   MODULE IMPORTS
##############################
# Import standard modules
import os
import signal
import sys
import json
import time
import datetime
import logging
import numpy as np

try:
	FileNotFoundError  # python3
except NameError:
	FileNotFoundError = IOError # python2

try:
	from urllib.request import urlopen
except ImportError:
	from urllib2 import urlopen

# Import flask modules
from flask import current_app, Blueprint, render_template, request, redirect, url_for, flash, g
from flask import send_file, send_from_directory, abort, make_response, jsonify
try:
	from flask import safe_join
except:
	from werkzeug.utils import safe_join

from werkzeug.utils import secure_filename

# Import celery modules
from celery import states
from celery.task.control import revoke

# Import Celery app
from caesar_rest.app import celery as celery_app
from caesar_rest import workers
from caesar_rest.workers import background_task
from caesar_rest import oidc
from caesar_rest import utils
from caesar_rest.decorators import custom_require_login
from caesar_rest import mongo

# Get logger
#logger = logging.getLogger(__name__)
from caesar_rest import logger

##############################
#   CREATE BLUEPRINTS
##############################
accounting_bp = Blueprint('accounting', __name__,url_prefix='/caesar/api/v1.0')
appstats_bp = Blueprint('appstats', __name__,url_prefix='/caesar/api/v1.0')

#=================================
#===      ACCOUNTING INFO 
#=================================
@accounting_bp.route('/accounting', methods=['GET'])
@custom_require_login
def get_accounting_info():
	""" Retrieve accounting info for this user """

	# - Get aai info
	#username= 'anonymous'
	#if ('oidc_token_info' in g) and (g.oidc_token_info is not None and 'email' in g.oidc_token_info):
	#	email= g.oidc_token_info['email']
	#	username= utils.sanitize_username(email)

	# - Get authenticated user storage identifier
	username = utils.get_storage_username()

	# - Get accounting info from DB
	res= {}	
	collection_name= username + '.accounting'
	try:
		coll= mongo.db[collection_name]
		cursor= coll.find_one({},projection={"_id":0})
		if res is None:
			errmsg= 'Accounting info retrieved from DB for user ' + username + ' is None!)'
			res['status']= errmsg
			return make_response(jsonify(res),404)
		else:
			res = dict(cursor)

	except Exception as e:
		errmsg= 'Failed to get accounting info for user ' + username + ' from DB (err=' + str(e) + ')'
		res['status']= errmsg
		return make_response(jsonify(res),404)
		
	return make_response(jsonify(res),200)



#=================================
#===      APP STATS INFO 
#=================================
@appstats_bp.route('/appstats', methods=['GET'])
@custom_require_login
def get_appstats_info():
	""" Retrieve app basic stats info cumulated over all users """

	# - Get aai info
	#username= 'anonymous'
	#if ('oidc_token_info' in g) and (g.oidc_token_info is not None and 'email' in g.oidc_token_info):
	#	email= g.oidc_token_info['email']
	#	username= utils.sanitize_username(email)

	# - Get authenticated user storage identifier
	username = utils.get_storage_username()
	
	# - Get app stats info from DB
	res= {}	
	collection_name= 'appstats'
	try:
		coll= mongo.db[collection_name]
		cursor= coll.find_one({},projection={"_id":0})
		if res is None:
			errmsg= 'App stats info retrieved from DB is None!)'
			res['status']= errmsg
			return make_response(jsonify(res),404)
		else:
			res = dict(cursor)

	except Exception as e:
		errmsg= 'Failed to get app stats info from DB (err=' + str(e) + ')'
		res['status']= errmsg
		return make_response(jsonify(res),404)
		
	return make_response(jsonify(res),200)
	

