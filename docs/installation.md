# Installation

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 46–98). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](archive/ORIGINAL_README.md).

## **Installation**  

### **Install dependencies**
To run caesar rest service you need to install the following tools:  

* Flask [https://palletsprojects.com/p/flask/]     
* uwsgi [https://uwsgi-docs.readthedocs.io/en/latest/index.html]   
* nginx [https://nginx.org/]   
* mongodb [https://www.mongodb.com/]   
* flask-pymongo python module [https://flask-pymongo.readthedocs.io/en/latest/]  
* structlog python module [https://www.structlog.org/en/stable/]     

For the Celery-based job management, you need to install celery, a broker and a result backend service:   

* celery [http://www.celeryproject.org/]   
* broker: rabbitmq [https://www.rabbitmq.com/]    
* result backend: redis [https://redis.io/] or mongodb [https://www.mongodb.com/]     

For the Kubernetes-based job management, you need to install the Kubernetes python client library:    

* kubernetes [https://pypi.org/project/kubernetes/]

For the Slurm-based job management, you need to install these python modules:    

* requests [https://docs.python-requests.org/en/master/]    
* jwt [https://pypi.org/project/jwt/]     

To enable OpenID Connect based authentication you need to install:    

* flask-oidc-ex python module fork [https://github.com/inaf-oact-ai/flask-oidc-ex]. The fork includes compatibility fixes required by current Flask/Werkzeug deployments. CAESAR-REST installs this dependency directly from the fork's `master` branch.

To enable log forwarding to a LogStash/ElasticSearch service, you need to install the filebeat service:    

* filebeat [https://www.elastic.co/guide/en/beats/filebeat/index.html]    

### **Package installation**
To build and install the package:    

* Create a local install directory, e.g. ```$INSTALL_DIR```
* Add installation path to your ```PYTHONPATH``` environment variable:   
  ``` export PYTHONPATH=$PYTHONPATH:$INSTALL_DIR/lib/python3.6/site-packages ```
* Build and install package:   
  ``` python3.6 setup.py sdist bdist_wheel```    
  ``` python3.6 setup build```   
  ``` python3.6 setup install --prefix=$INSTALL_DIR```   

All dependencies will be automatically downloaded and installed in ```$INSTALL_DIR```.   
     
To use package scripts:

* Add binary directory to your ```PATH``` environment variable:   
  ``` export PATH=$PATH:$INSTALL_DIR/bin ```    

