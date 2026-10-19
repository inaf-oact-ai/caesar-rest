##############################
#   MODULE IMPORTS
##############################
# - Import standard modules
import os
import sys
import json
import time
import datetime
import logging
import numpy as np
import hashlib
import tarfile
import subprocess
import uuid
import re

# - Import Flask modules
from flask import current_app, g, abort

# - Import astro modules
from astropy.io import fits
from astropy.visualization import ZScaleInterval, LinearStretch, ImageNormalize, MinMaxInterval
import regions

# - Graphics modules
import matplotlib as mpl
mpl.rcParams['xtick.direction'] = 'in'
mpl.rcParams['ytick.direction'] = 'in'

from matplotlib import pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable

# - Get logger
from caesar_rest import logger

def get_uuid():
	""" Return a uuid code """
	return uuid.uuid4().hex

def tarsum(input_filename, output_filename, hash_type='md5'):
	"""
		input_file  - A FILE object to read the tar file from.
		hash - The name of the hash to use. Must be supported by hashlib.
		output_file - A FILE to write the computed signatures to.
	"""

	# - Open tar file
	try:
		#tar= tarfile.open(mode="r|*", fileobj=input_file)
		tar= tarfile.open(name=input_filename,mode='r|*')
	except Exception as e:
		logger.error("Failed to open tar file %s (err=%s)!" % (input_file,e))
		return -1		

	# - Open output file
	output_file = open(output_filename, "w")

	# - Compute checksums for all files and write to output file
	chunk_size = 100*1024
	store_digests = {}
 
	for item in tar:
		if not item.isfile():
			continue
		f = tar.extractfile(item)
		h = hashlib.new(hash_type)
		data = f.read(chunk_size)
		while data:
			h.update(data)
			data = f.read(chunk_size)

		output_file.write("%s  %s\n" % (h.hexdigest(), item.name))

	return 0


def make_tar(output_filename, source_dir):
	""" Create a tar file """
	with tarfile.open(output_filename, "w:gz") as tar:
		tar.add(source_dir, arcname=os.path.basename(source_dir))


def make_staged_pipeline_tar(output_filename, source_dir):
	"""Archive a staged pipeline job without duplicating private input data.

	Retain input/staging.json, execution metadata, and scientific outputs.
	Do not follow symlinks or include existing job archives.
	"""
	import tempfile

	source_dir = os.path.abspath(source_dir)
	output_filename = os.path.abspath(output_filename)
	root_name = os.path.basename(source_dir)

	if not os.path.isdir(source_dir) or os.path.islink(source_dir):
		raise ValueError("Invalid staged pipeline workspace")

	def archive_filter(member):
		name = member.name
		relative = os.path.relpath(name, root_name)

		# Never archive symlinks, including links outside the workspace.
		if member.issym() or member.islnk():
			return None

		# Exclude existing archives.
		if relative.endswith('.tar.gz'):
			return None

		# Keep only the staging manifest from the private input directory.
		if relative == 'input':
			return member

		if relative.startswith('input/'):
			if relative != 'input/staging.json':
				return None

		return member

	# Create outside the workspace to avoid including a partial archive.
	parent_dir = os.path.dirname(source_dir)
	fd, temporary_path = tempfile.mkstemp(
		prefix='.pipeline-archive-',
		suffix='.tmp',
		dir=parent_dir
	)

	try:
		with os.fdopen(fd, 'wb') as output:
			with tarfile.open(fileobj=output, mode='w:gz') as tar:
				tar.add(
					source_dir,
					arcname=root_name,
					recursive=True,
					filter=archive_filter
				)

		os.replace(temporary_path, output_filename)

	finally:
		if os.path.exists(temporary_path):
			os.unlink(temporary_path)

def sanitize_username(s):
	""" Sanitize username removing @ and . and replacing with underscores """

	username= s.replace('@', '_')
	username= username.replace('.', '_')

	return username

def get_storage_username():
	"""
	Return a readable, user-specific storage identifier.

	AAI enabled:
		<preferred_username>_<OIDC_subject_UUID>

	AAI disabled:
		anonymous

	The identifier is used for filesystem directories and
	user-specific MongoDB collections.
	"""

	if not current_app.config.get('USE_AAI', False):
		return 'anonymous'

	claims = getattr(g, 'oidc_token_info', None)

	if not isinstance(claims, dict):
		abort(401, description='Authenticated OIDC identity required')

	issuer = claims.get('iss')
	subject = claims.get('sub')

	if not isinstance(issuer, str) or not issuer.strip():
		abort(401, description='OIDC issuer missing')

	if not isinstance(subject, str) or not subject.strip():
		abort(401, description='OIDC subject missing')

	# Keycloak uses UUIDs for user subjects.
	try:
		subject_uuid = str(uuid.UUID(subject))
	except (ValueError, AttributeError, TypeError):
		abort(401, description='Invalid Keycloak user subject')

	# Use the human-readable Keycloak username.
	username = claims.get('preferred_username')

	if not isinstance(username, str) or not username.strip():
		username = 'user'

	# Restrict the directory component to safe ASCII characters.
	username = re.sub(
		r'[^a-zA-Z0-9_-]',
		'_',
		username.strip()
	)

	username = username.strip('_-')[:64]

	if not username:
		username = 'user'

	return username + '_' + subject_uuid

def get_dir_size(dirname,unit='K'):
	""" Return the directory size in specified units """
		
	cmd= 'du'
	cmd_args= '-shB' + unit
	dirsize_str= subprocess.check_output([cmd,cmd_args, dirname]).split()[0].decode('utf-8')
	dirsize= float(dirsize_str.replace(unit,''))
	return dirsize


def plot_img_and_regions(imgfile, regionfiles=[], zmin=0, zmax=0, cmap="afmhot", contrast=0.3, save=False, outfile="plot.png"):
	""" Plot input FITS and regions """

	#===========================
	#==   READ REGION
	#===========================
	regs= []
	for regionfile in regionfiles:
		logger.info("Reading region file %s ..." % regionfile)
		try:
			region_list= regions.read_ds9(regionfile)
		except Exception as e:
			logger.warning("read_ds9 failed (err=%s), trying another method..." % (str(e)))	
			region_list= regions.Regions.read(regionfile, format='ds9')
			
		regs.extend(region_list)

	#===========================
	#==   READ IMAGE
	#===========================
	# - Read fits
	try:
		hdu= fits.open(imgfile)
		data= hdu[0].data
		header= hdu[0].header
	except:
		logger.error("Failed to open input img %s!" % imgfile)
		return -1

	# - Remove 3 and 4 channels
	nchan= len(data.shape)
	logger.info("Input image has %d channels..." % nchan)
	if nchan==4:
		data= data[0,0,:,:]
	elif nchan==3:
		data= data[0,:,:]
	else:
		if nchan!=2:	
			logger.error("Invalid/unrecognized number of channels (%d)!" % nchan)
			return -1
		
	# - Get image units	
	bunit= 'z'
	if 'BUNIT' in header:
		bunit= header['BUNIT']

	# - Set stretch	
	stretch= LinearStretch()
	norm = ImageNormalize(data, interval=ZScaleInterval(contrast=contrast), stretch=stretch)
	
	#===========================
	#==   PLOT IMAGE
	#===========================
	# - Plot image	
	fig = plt.figure(figsize=(10,10))
	ax = fig.add_subplot(1, 1, 1)
	if zmin<zmax:
		im= ax.imshow(data, origin='lower', vmin=zmin, vmax=zmax, cmap=cmap, norm=norm)
	else:
		im= ax.imshow(data, origin='lower', cmap=cmap, norm=norm)
	
	# - Set axis titles
	ax.set_xlabel('x',size=18, labelpad=0.7)
	ax.set_ylabel('y',size=18)

	# - Draw color bar
	color_bar_label= 'Brightness (' + bunit + ')'
	cb= fig.colorbar(im, orientation="vertical", pad=0.01, fraction=0.047)
	cb.set_label(color_bar_label, y=1.0, ha='right',size=12)
	cb.ax.tick_params(labelsize=12) 

	# - Set ticks
	plt.tick_params(axis='x', labelsize=14)
	plt.tick_params(axis='y', labelsize=14)

	# - Superimpose regions
	region_color= "lime"
	region_style= "dashed"
	#region_style= "solid"

	if regionfile!="":
		logger.debug("Superimposing region ...")
		for r in regs:
			r.plot(ax=ax, color=region_color, linestyle=region_style)
	
	# - Save or display
	if save:
		plt.savefig(outfile, bbox_inches='tight')
	else:
		plt.show()

	return 0




