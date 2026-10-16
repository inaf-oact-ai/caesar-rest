
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

try:
	FileNotFoundError  # python3
except NameError:
	FileNotFoundError = IOError # python2

try:
	from urllib.request import urlopen
except ImportError:
	from urllib2 import urlopen

#import urllib.request

# Import Flask
from flask import Flask
from flask import flash, request, redirect, render_template, url_for
from flask import send_file, send_from_directory, abort
try:
	from flask import safe_join
except:
	from werkzeug.utils import safe_join
	
from werkzeug.utils import secure_filename

# Import Celery
from caesar_rest import celery

# Import config class
from caesar_rest.config import Config

from pymongo import MongoClient


## Get logger
#logger = logging.getLogger(__name__)
from caesar_rest import logger

##############################
#   CELERY APP CREATION
############################## 
def configure_celery_app(app):
	""" Create a Celery app """
    
	# - Configure app from Flask config
	celery.conf.update(app.config)

	# - Subclass task
	TaskBase = celery.Task
	class ContextTask(TaskBase):
		abstract = True
	 
		def __call__(self, *args, **kwargs):
			with app.app_context():
				return TaskBase.__call__(self, *args, **kwargs)
    
	celery.Task = ContextTask
	
	
##############################
#   FLASK APP CREATION 
##############################
##def create_app(cfg,dm,jc):
def create_app(cfg,jc):
	""" Create app """

	# - Create app
	app = Flask(__name__,instance_relative_config=True)

	# - Configure app from class 
	app.config.from_object(cfg)
	
	# - Add helper classes to app
	app.config['jobcfg'] = jc

	# - Configure Celery app
	configure_celery_app(app)

	# - Register routes as blueprints
	from caesar_rest.index_route import index_bp
	from caesar_rest.upload_route import upload_bp
	from caesar_rest.download_route import download_id_bp
	from caesar_rest.download_route import fileids_bp
	from caesar_rest.download_route import delete_id_bp
	from caesar_rest.job_route import job_bp, job_status_bp, job_output_bp, job_cancel_bp
	from caesar_rest.job_route import job_catalog_bp, job_catalog_file_bp, job_component_catalog_bp, job_component_catalog_file_bp, job_preview_bp, job_preview_file_bp
	from caesar_rest.job_route import dataset_names_bp
	from caesar_rest.dataset_route import registry_bp
	from caesar_rest.app_route import app_names_bp, app_describe_bp
	from caesar_rest.accounting_route import accounting_bp, appstats_bp
	app.register_blueprint(index_bp)
	app.register_blueprint(upload_bp)
	app.register_blueprint(download_id_bp)
	app.register_blueprint(fileids_bp)
	app.register_blueprint(delete_id_bp)
	app.register_blueprint(job_bp)
	app.register_blueprint(job_status_bp)
	app.register_blueprint(job_output_bp)
	app.register_blueprint(job_catalog_bp)
	app.register_blueprint(job_catalog_file_bp)
	app.register_blueprint(job_component_catalog_bp)
	app.register_blueprint(job_component_catalog_file_bp)
	app.register_blueprint(job_preview_bp)
	app.register_blueprint(job_preview_file_bp)
	app.register_blueprint(job_cancel_bp)
	app.register_blueprint(app_names_bp)
	app.register_blueprint(app_describe_bp)
	app.register_blueprint(accounting_bp)
	app.register_blueprint(appstats_bp)
	app.register_blueprint(dataset_names_bp)
	app.register_blueprint(registry_bp)

	return app


