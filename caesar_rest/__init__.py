#! /usr/bin/env python

__title__ = 'caesar_rest'
__version__ = '1.8.0'
__author__ = 'Simone Riggi'
__license__ = 'GPL3'
__date__ = '2020-04-17'
__copyright__ = 'Copyright 2020 by Simone Riggi - INAF'


# - Create the standard Logger
import logging
import logging.handlers
#import logging.config
#logging.basicConfig(format="%(asctime)-15s %(levelname)s - %(message)s",datefmt='%Y-%m-%d %H:%M:%S')
#logger= logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)

# - Create the struct logger
import structlog

structlog.configure(
	processors=[
		structlog.stdlib.filter_by_level,
		structlog.processors.TimeStamper(fmt="iso"),
#		structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
		structlog.stdlib.add_logger_name,
		structlog.stdlib.add_log_level,
		structlog.stdlib.PositionalArgumentsFormatter(),
		structlog.processors.StackInfoRenderer(),
		structlog.processors.format_exc_info,
		structlog.processors.UnicodeDecoder(),
		structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
#		structlog.stdlib.render_to_log_kwargs
	],
	context_class=structlog.threadlocal.wrap_dict(dict),
	logger_factory=structlog.stdlib.LoggerFactory(),
	wrapper_class=structlog.stdlib.BoundLogger,
	cache_logger_on_first_use=True,
)


# - Define console logger
formatter_stream = structlog.stdlib.ProcessorFormatter(
	processor= structlog.dev.ConsoleRenderer()
)
handler_stream= logging.StreamHandler()
handler_stream.setFormatter(formatter_stream)

# - Define file json logger
#formatter_file= structlog.stdlib.ProcessorFormatter(
#	processor=structlog.processors.JSONRenderer(),
#)
#handler_file= logging.handlers.RotatingFileHandler(
#	LOG_FILE_PATH, 
#	maxBytes=5*1024*1024,
#	backupCount=2 
#)
#handler_file.setFormatter(formatter_file)   # In theory, jsonlogger.JsonFormatter() could be used instead with custom override methods that allow us to re-order keys to how we'd like


# - Define root logger and add handlers
logger= structlog.getLogger(__name__)
logger.addHandler(handler_stream)
#logger.addHandler(handler_file)
logger.setLevel("INFO")

#logging.basicConfig(
#	format="%(asctime)-15s %(levelname)s - %(message)s",
#	datefmt='%Y-%m-%d %H:%M:%S',
#	handlers=[handler],
#	level=logging.INFO,
#)

logger.info("This is caesar_rest {0}-({1})".format(__version__, __date__))


# - Create Celery only when its dependency is available.
# - Slurm/Kubernetes installations do not require Celery.
celery = None

try:
	from celery import Celery

	celery = Celery(
		__name__,
		config_source='caesar_rest.celery_config'
	)

except ImportError:
	logger.info(
		"Celery is not installed; legacy Celery backend is unavailable"
	)

# - Create OIDC (without connecting to app)
oidc= None
try:
	from flask_oidc_ex import OpenIDConnect
	oidc = OpenIDConnect()

except:
	logger.warn("flask_oidc module not found, can't create OpenIDConnect(), no AAI will be used (hint: install flask_oidc)")

# - Create MongoDB engine
mongo= None
try:
	from flask_pymongo import PyMongo
	mongo= PyMongo()

except Exception as e:
	errmsg= 'flask_pymongo module not found or failed to create mongo instance (err=' + str(e) + ')'
	logger.error(errmsg)
	raise ImportError(errmsg)


# - Create Kubernetes job manager class (to be initialized later)
jobmgr_kube= None
try:
	from caesar_rest.kube_client import KubeJobManager
	jobmgr_kube= KubeJobManager()

except Exception as e:
	errmsg= 'Kubernetes modules not found or failed to create KubeJobManager instance (err=' + str(e) + ')'
	logger.warn(errmsg)

# - Create Slurm job manager class (to be initialized later)
jobmgr_slurm= None
try:
	from caesar_rest.slurm_client import SlurmJobManager
	jobmgr_slurm= SlurmJobManager()

except Exception as e:
	errmsg= 'Slurm required modules not found or failed to create SlurmJobManager instance (err=' + str(e) + ')'
	logger.warn(errmsg)
	


