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
import subprocess
import json
import ast
import yaml

# Import flask modules
from flask import current_app, g

# Import caesare rest momdules
from caesar_rest import oidc
from caesar_rest import mongo
from caesar_rest import utils

# Get logger
#logger = logging.getLogger(__name__)
from caesar_rest import logger

##############################
#   APP CONFIGURATOR
##############################
class Option(object):

	#def __init__(self, name, mandatory=False, description='', category='', subcategory='', advanced=False):
	#	self.name= name
	#	self.mandatory= mandatory
	#	self.value_required= False
	#	self.value= None
	#	self.value_type= type(None)
	#	self.description= description
	#	self.advanced= advanced	
	#	self.category= category
	#	self.subcategory= subcategory	
	#	self.enum= False
	#	self.allowed_values= []
		
	def __init__(self, name, mandatory=False, description='', category='', subcategory='', advanced=False, default_value=None):
		self.name= name
		self.mandatory= mandatory
		self.value_required= False
		self.value= None
		self.value_type= type(None)
		self.description= description
		self.advanced= advanced	
		self.category= category
		self.subcategory= subcategory	
		self.enum= False
		self.allowed_values= []
		self.default_value= default_value

	def to_argopt(self):
		""" Convert option to cmdline format """
		
		if self.value_required:
			argopt= '--' + self.name + '=' + str(self.value)
		else:
			argopt= '--' + self.name

		return argopt

	def to_dict(self):
		""" Convert option to dictionary """
		
		if self.value_required:
			if self.enum:
				d= {
					self.name: {
						"mandatory": self.mandatory,
						"type": self.value_type.__name__,
						"description": self.description,
						"advanced": int(self.advanced),
						"category": self.category,
						"subcategory": self.subcategory,
						"default": self.default_value,
						"allowed_values": self.allowed_values,
						"enum": self.enum
					}
				}
			else:
				d= {
					self.name: {
						"mandatory": self.mandatory,
						"type": self.value_type.__name__,
						"description": self.description,
						"advanced": int(self.advanced),
						"category": self.category,
						"subcategory": self.subcategory,
						"default": self.default_value,
						"min": self.min_value,
						"max": self.max_value,
						"enum": self.enum # could be removed for non-enum options
					}
				}
		else:
			d= {
				self.name: {
					"mandatory": self.mandatory,
					"type": "none",
					"description": self.description,
					"advanced": int(self.advanced),
					"category": self.category,
					"subcategory": self.subcategory,
					"enum": self.enum # could be removed for non-enum options
				}
			}
			
			if self.default_value is not None:
				d[self.name]["default"] = self.default_value	
			
		return d
	

class ValueOption(Option):

	def __init__(self, name, value, value_type, mandatory=False, description='', category='', subcategory='', advanced=False, default_value='', min_value='', max_value=''):
		""" Return value option """
		Option.__init__(self,name,mandatory,description,category,subcategory,advanced)
		self.value= value
		self.value_required= True
		self.value_type= value_type
		self.default_value= default_value
		self.min_value= min_value
		self.max_value= max_value
		self.enum= False

class EnumValueOption(Option):

	def __init__(self, name, value, value_type, allowed_values, mandatory=False, description='', category='', subcategory='', advanced=False, default_value=''):
		""" Return value option """
		Option.__init__(self,name,mandatory,description,category,subcategory,advanced)
		self.value= value
		self.value_required= True
		self.value_type= value_type
		self.default_value= default_value
		self.enum= True
		self.allowed_values= allowed_values


class AppConfigurator(object):
	""" Class to define base app configurator """
  
	def __init__(self, app_name="unknown"):
		""" Constructor"""

		self.app_name= app_name
		self.job_options= ''
		self.data_inputs= ''
		self.cmd= ''
		self.cmd_args= []
		self.cmd_mode= ''
		self.validation_status= ''
		self.valid_options= {}
		self.options= []
		self.option_value_transformer= {}
		self.batch_processing_support= False
		self.run_options= {
			"ncores": 1,
			"nproc": 1,
			"container_variant": ""
		}
		self.job_outputs= {}
		self.description= ""
		self.tool_categories= []
		self.input_requirements= {}
		self.limitations= []

	def describe_dict(self):
		""" Return a dictionary describing valid options """
			
		# - Init dictionary	
		#d= {}
		d= {
			"name": self.app_name,
			"description": self.description,
			"tool_categories": self.tool_categories,
			"input_requirements": self.input_requirements,
			"job_options": {},
			"job_outputs": self.job_outputs,
			"limitations": self.limitations
		}
		
		# - Fill job options
		for opt_name, option in self.valid_options.items():
			option_dict= option.to_dict()
			#d.update(option_dict)
			d["job_options"].update(option_dict)

		return d

	def describe_str(self):
		""" Return a json string describing valid options """
			
		d= self.describe()
		return json.dumps(d)

	def describe_json(self):
		""" Return a json dictionary describing valid options """
			
		json_str= self.describe_str()
		return json.loads(json_str)

	def set_ncores_from_options(self):
		""" Set the number of cores from parsed options (to be overridden) """
		
		self.run_options["ncores"]= 1

	def set_nproc_from_options(self):
		""" Set the number of MPI proc from parsed options (to be overridden) """
		
		self.run_options["nproc"]= 1


	def get_transformed_option_value(self, opt_name, opt_value):
		""" Returns same option value or transformed option value (if a transformed function is defined in the dictionary) """

		if not self.option_value_transformer:
			return opt_value
		if not opt_name in self.option_value_transformer:
			return opt_value
		return self.option_value_transformer[opt_name](opt_value)


	def set_data_input_option_value(self):
		""" Set app input option value (to be overridden in derived classes) """
			
		# Left empty as to be overridden in derived classes
		

	def validate(self, job_options, data_inputs):
		""" Validate job input """

		logger.info("Validating given inputs ...", action="submitjob")

		# - Check if job inputs are empty
		if not job_options:		
			self.validation_status= 'Empty job inputs given!'
			logger.warn(self.validation_status, action="submitjob")
			return False

		# - Check data inputs
		#if not data_inputs or data_inputs is None:
		if data_inputs is None or (isinstance(data_inputs,list) and not data_inputs) or (isinstance(data_inputs,str) and data_inputs==""):
			self.validation_status= 'Empty or null data input given!'
			logger.warn(self.validation_status, action="submitjob")
			return False

		self.data_inputs= data_inputs

		# - Convert json string to dictionary
		#print("type(job_options)")
		#print(type(job_options))
		#print(job_options)

		if not isinstance(job_options,dict):
			self.validation_status= 'Given job inputs data is not a dictionary!'
			logger.warn(self.validation_status, action="submitjob")
			return False

		try:
			self.job_options= yaml.safe_load(json.dumps(job_options))

		except ValueError:
			self.validation_status= 'Failed to parse job inputs as json dictionary!'
			logger.warn(self.validation_status, action="submitjob")
			return False

		#print("type(self.job_options)")
		#print(type(self.job_options))
		#print(self.job_options)

		# - Validate options 
		valid= self.validate_options()
		print("--> %s args" % self.cmd)
		print(self.cmd_args)

		# - Set input data option
		self.set_data_input_option_value()

		# - Set ncores option
		self.set_ncores_from_options()

		# - Set nproc option
		self.set_nproc_from_options()

		
		return valid


	def normalize_bool_option_value(self, opt_name, value):
		"""Normalize a boolean option value.

		Accept native booleans and string representations "true"/"false".
		Reject all other values.
		"""

		if isinstance(value, bool):
			return value

		if isinstance(value, str):
			value_norm= value.strip().lower()

			if value_norm == "true":
				logger.warn(
					"Bool option %s was provided as string '%s'; "
					"normalizing to True." % (opt_name, value),
					action="submitjob"
				)
				return True

			if value_norm == "false":
				logger.warn(
					"Bool option %s was provided as string '%s'; "
					"normalizing to False." % (opt_name, value),
					action="submitjob"
				)
				return False

		return None

	def validate_options(self):
		""" Validate parsed options against valid expected options (provided in derived class) """

		# - Validate options
		for opt_name, option in self.valid_options.items():
			option_given= opt_name in self.job_options

			# - Check if mandatory option is given
			mandatory= option.mandatory
			if mandatory and not option_given:
				self.validation_status= ''.join(["Mandatory option ",opt_name," not present!"])
				logger.warn(self.validation_status, action="submitjob")
				return False
	
			# - Skip if not given, unless this is a boolean option with an explicit default value
			if not option_given:
				if option.value_required:
					continue

				# - Retro-compatibility:
				# if default_value is None, keep old behavior and skip missing bool options
				if option.default_value is None:
					continue

				# - Boolean options must have boolean defaults
				if not isinstance(option.default_value, bool):
					self.validation_status= ''.join([
						"Default value for bool option ",
						opt_name,
						" is not a boolean!"
					])
					logger.warn(self.validation_status, action="submitjob")
					return False

				# - Use the configured default as if it had been provided in job_options
				self.job_options[opt_name]= option.default_value
				option_given= True

			# - Check if required value
			value_required= option.value_required
			if value_required:
				# - Check for value type
				expected_val_type= option.value_type
				parsed_value= self.job_options[opt_name]
				parsed_value_type= type(parsed_value)
				if not isinstance(parsed_value, expected_val_type):
					#self.validation_status= ''.join(["Option ",opt_name," expects a ",str(expected_val_type)," value type and not a ",str(parsed_value_type)," !"])
					#logger.warn(self.validation_status, action="submitjob")
					#return False
					self.validation_status= ''.join(["Option ",opt_name," expects a ",str(expected_val_type)," value type and not a ",str(parsed_value_type),", casting it..."])
					logger.warn(self.validation_status, action="submitjob")
					try:
						parsed_value_casted= expected_val_type(parsed_value)
						parsed_value= parsed_value_casted
					except:
						self.validation_status= ''.join(["Failed to cast option ",opt_name," to type ",str(expected_val_type)," !"])
						logger.warn(self.validation_status, action="submitjob")
						return False

				# - Check if value is among allowed values for enum
				if option.enum:
					if parsed_value not in option.allowed_values:
						self.validation_status= ''.join(["Option ",opt_name," value ",str(parsed_value)," is not among valid enumerations!"])
						logger.warn(self.validation_status, action="submitjob")
						return False

				# - Return option value transformed (if transform function is defined in derived classes) or the same option value
				opt_value_str= str(parsed_value)
				transf_opt_value_str= self.get_transformed_option_value(opt_name,opt_value_str)
				if transf_opt_value_str=='':
					logger.warn("Transformed option value is empty string, failed validation, check logs!", action="submitjob")
					return False

				# - Add option
				if option.enum:
					value_option= EnumValueOption(
						opt_name,
						transf_opt_value_str,
						expected_val_type,	
						option.allowed_values,
						mandatory,
						option.description,
						option.category,
						option.subcategory,
						option.advanced,
						option.default_value
					)
				else:
					value_option= ValueOption(
						opt_name,
						transf_opt_value_str,
						expected_val_type,
						mandatory,
						option.description,
						option.category,
						option.subcategory,
						option.advanced,
						option.default_value,
						option.min_value,
						option.max_value
					)
				self.options.append(value_option)

				# - Convert to cmd arg format
				argopt= value_option.to_argopt()
				self.cmd_args.append(argopt)
			
			else: # No value required

				# - Check boolean value given
				#parsed_value= self.job_options[opt_name]
				#parsed_value_type= type(parsed_value)
				#if not isinstance(parsed_value, bool):
				#	self.validation_status= ''.join(["Failed to parse bool option ",opt_name," (parsed value type is not a boolean)!"])
				#	logger.warn(self.validation_status, action="submitjob")
				#	return False

				# - Normalize and validate boolean value
				parsed_value_raw= self.job_options[opt_name]
				parsed_value= self.normalize_bool_option_value(
					opt_name,
					parsed_value_raw
				)

				if parsed_value is None:
					self.validation_status= ''.join([
						"Failed to parse bool option ",
						opt_name,
						" (value=",
						repr(parsed_value_raw),
						", type=",
						str(type(parsed_value_raw)),
						")!"
					])
					logger.warn(
						self.validation_status,
						action="submitjob"
					)
					return False

				# - Store normalized value back in parsed job options
				self.job_options[opt_name]= parsed_value

				# - Add option only if parsed flag is True, if not skip
				if not parsed_value:
					continue

				# - Add option
				bool_option= Option(
					opt_name,
					mandatory,
					option.description,
					option.category,
					option.subcategory,
					option.advanced,
					option.default_value
				)
				self.options.append(bool_option)

				# - Convert to cmd arg format
				argopt= bool_option.to_argopt()
				self.cmd_args.append(argopt)

		return True

