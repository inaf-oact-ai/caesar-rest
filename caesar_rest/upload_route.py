##############################
#   MODULE IMPORTS
##############################
# Import standard modules
import os
import sys
import json
import time
import datetime
import logging
import numpy as np
import uuid

try:
	FileNotFoundError  # python3
except NameError:
	FileNotFoundError = IOError # python2

try:
	from urllib.request import urlopen
except ImportError:
	from urllib2 import urlopen

# import Flask modules
from flask import current_app, Blueprint, flash, request, redirect, render_template, url_for, g
from flask import send_file, send_from_directory, abort, make_response, jsonify
try:
	from flask import safe_join
except:
	from werkzeug.utils import safe_join
	
#from flask_api import status
from werkzeug.utils import secure_filename
from caesar_rest import oidc
from caesar_rest import utils
from caesar_rest.decorators import custom_require_login
#from caesar_rest import db
#from caesar_rest.data_model import DataFile #, DataCollection 
from caesar_rest import mongo

# Get logger
#logger = logging.getLogger(__name__)
from caesar_rest import logger

##############################
#   CREATE BLUEPRINT
##############################
#ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif', 'fits', 'json'])

def allowed_file(filename):
	#return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
	return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['UPLOAD_ALLOWED_FILE_FORMATS']

upload_bp = Blueprint('upload', __name__, url_prefix='/caesar/api/v1.0')

@upload_bp.route('/upload', methods=['POST'])
@custom_require_login
def upload_file():
	""" Upload image """

	# - Get aai info
	#username= 'anonymous'
	#if ('oidc_token_info' in g) and (g.oidc_token_info is not None and 'email' in g.oidc_token_info):
	#	email= g.oidc_token_info['email']
	#	username= utils.sanitize_username(email)
		
	# - Get authenticated user storage identifier
	username = utils.get_storage_username()

	# - Init response
	res= {
		'filename_orig': '',
		'tag': '',
		'format': '',
		'size': '',
		'uuid': '',
		#'path': '',
		'date': '',
		'status': ''
	}
	
	# - Check for file
	logger.info("Checking for file key in request ...")
	if 'file' not in request.files:
		errmsg= "Missing file field in request!"
		flash(errmsg)
		logger.warn(errmsg, action="upload", user=username)
		res['status']= errmsg
		return make_response(jsonify(res),400)
		
	f = request.files['file']
	if not f:
		errmsg= "No file retrieved from request!"
		flash(errmsg)
		logger.warn(errmsg, action="upload", user=username)
		res['status']= errmsg
		return make_response(jsonify(res),400)
		
	if f.filename == '':
		errmsg= "No file selected for uploading"
		flash(errmsg)
		logger.warn(errmsg)
		res['status']= errmsg
		return make_response(jsonify(res),400)
		
	if not allowed_file(f.filename):
		errmsg= "File format not allowed, allowed file types are: {png|jpg|jpeg|gif|fits|json}"
		flash(errmsg)
		logger.warn(errmsg, action="upload", user=username)
		res['status']= errmsg
		return make_response(jsonify(res),415)
		
	filename= secure_filename(f.filename)
	file_ext= os.path.splitext(filename)[1].split('.')[1]
	file_uuid= uuid.uuid4().hex
	filename_dest= '.'.join([file_uuid,file_ext])
	filename_dest_dir= current_app.config['UPLOAD_FOLDER'] + '/' + str(username)
	filename_dest_fullpath= os.path.join(filename_dest_dir, filename_dest)
	
	file_tag = ''
	if request.form:
		if 'tag' in request.form:
			file_tag= request.form['tag']
		else:
			logger.info("No tag information given in request, set empty...", action="upload", user=username)
	else:
		logger.warn("form not present in request...", action="upload", user=username)

	# - Create username directory if not existing before
	logger.info("Creating username directory if not existing before ...", action="upload", user=username)
	try: 
		os.makedirs(filename_dest_dir)
	except OSError:
		if not os.path.isdir(filename_dest_dir):
			errmsg= "Failed to create file destination dir!"
			flash(errmsg)
			logger.warn(errmsg, action="upload", user=username)
			res['status']= errmsg
			return make_response(jsonify(res),500)
	
	# - Save file
	logger.info("Saving file %s ..." % filename_dest_fullpath, action="upload", user=username)
	f.save(filename_dest_fullpath)
	flash('File successfully uploaded')

	# - Set file info
	now = datetime.datetime.now()
	file_upload_date= now.isoformat()
	file_size= os.path.getsize(filename_dest_fullpath)/(1024.*1024.) # in MB

	res['filename_orig']= filename
	res['tag'] = file_tag
	res['format']= file_ext
	res['size']= file_size
	res['uuid']= file_uuid
	#res['path']= filename_dest_fullpath # removed for security reasons
	res['date']= file_upload_date
	res['status']= 'File uploaded with success'

	# - Register file in MongoDB
	logger.info("Creating data file object ...", action="upload", user=username)
	data_fileobj= {
		"filepath": filename_dest_fullpath,
		"fileid": file_uuid,
		"filename_orig": filename,
		"fileext": file_ext,	
		"filesize": file_size,
		"filedate": file_upload_date, 
		"metadata": '', # FIX ME
		"tag": file_tag
	}

	collection_name= username + '.files'
		
	try:			
		logger.info("Creating or retrieving data collection %s for user %s ..." % (collection_name, username), action="upload", user=username)
		data_collection= mongo.db[collection_name]

		logger.info("Adding data file obj to collection ...", action="upload", user=username)
		try:
			item_id= data_collection.insert(data_fileobj)
		except Exception as ex:
			logger.warn("MongoDB insert() method failed with err (%s), trying with insert_one() ..." % str(ex), action="upload", user=username)		
			item_id= data_collection.insert_one(data_fileobj)

	except Exception as e:
		errmsg= "File " + filename_dest_fullpath + " uploaded but failed to be registered in DB (err=" + str(e) + ")!"
		logger.warn(errmsg, action="upload", user=username)
		flash(errmsg)
		res['status']= 'File uploaded but failed to be registered in DB'
		return make_response(jsonify(res),500)

	return make_response(jsonify(res),200)

