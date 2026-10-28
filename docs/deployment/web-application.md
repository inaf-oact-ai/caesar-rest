# Web application in production

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 379–504). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

#### **Run the application in production**   
In a production environment you can run the application behind a nginx+uwsgi (or nginx+gunicorn) server. In the `config` directory of the repository you can find sample files to create and configure required services. For example:  

* Start the application with uwsgi:   
     
  uwsgi --wsgi-file $INSTALL_DIR/bin/run_app.py --callable app [WSGI_CONFIG_FILE]

  where ```WSGI_CONFIG_FILE``` is a configuration file (.ini format) for uwsgi. A sample configuration file is provided in the `config/uwgsi` directory:   
  
  ```
  [uwsgi]
  processes = 4   
  threads = 2   
  socket = ./run/caesar-rest.sock   
  ;socket = :5000
  ;http-socket = :5000
  socket-timeout = 65
  
  buffer-size = 32768  
  master = true   
  chmod-socket = 660   
  vacuum = true  
  die-on-term = true  
  ```
  
  Alternatively you can configure options from command line, e.g.:    
  
   ```uwsgi --uid=[RUNUSER] --gid=[RUNUSER] --binary-path /usr/local/bin/uwsgi --wsgi-file=$INSTALL_DIR/bin/run_app.py --callable=app --pyargv=[APP_ARGS] --workers=[NWORKERS] --enable-threads --threads=[NTHREADS] --http-socket="0.0.0.0:[PORT]" --http-timeout=[SOCKET_TIMEOUT] --http-enable-proxy-protocol --http-auto-chunked --socket-timeout=[SOCKET_TIMEOUT] --master --chmod-socket=660 --chown-socket=[RUNUSER] --buffer-size=[BUFFER_SIZE] --vacuum --die-on-term ```
  
  where ```APP_ARGS``` are the application command line options described in the previous paragraph and ```RUNUSER``` is the username chosen for running the service. The other options are described in the uwsgi online documentation.    
  
  In production you may want to run this as a system service: 
  
  - Create an `/etc/systemd/system/caesar-rest.service` systemd service file, for example following the example provided in the `config/uwsgi` directory:       
       
    ```
    [Unit]
    Description=uWSGI instance to serve caesar-rest application    
    After=network.target caesar-workers.target   

    [Service]
    User=caesar  
    Group=www-data   
    WorkingDirectory=/opt/caesar-rest  
    Environment="PATH=$INSTALL_DIR/bin"   
    Environment="PYTHONPATH=$INSTALL_DIR/lib/python2.7/site-packages"  
    ExecStart=/usr/bin/uwsgi --wsgi-file $INSTALL_DIR/bin/run_app.py --callable app --ini /opt/caesar-rest/config/uwsgi.ini

    [Install]   
    WantedBy=multi-user.target    
    ```   
    
   - Start the service:   
     ```sudo systemctl caesar-rest.service start```    

   Alternatively, you can use the Docker container `sriggi/caesar-rest:devel` (see https://hub.docker.com/r/sriggi/caesar-rest) and deploy it with DockerCompose or Kubernetes (see the configuration files under the repository ```config``` directory. All application command line options described in the previous section can be configured from container env variables.        

* Start the nginx service:

  - Create a `/etc/nginx/conf.d/nginx.conf` configuration file (see example file provided in the `config/nginx` directory):      

    ```
    server {   
      listen 8080;   
      client_max_body_size 1000M;   
      sendfile on;    
      keepalive_timeout 0;   
      location / {   
        include uwsgi_params;    
        uwsgi_pass unix:/opt/caesar-rest/run/caesar-rest.sock;   
      }       
    }    
    ```
  
    With this sample configuration the nginx server will listen at port 8080 and call the caesar-rest application via socket. An alternative configuration could be:    
    
    ```
    upstream backend {
      least_conn;  # load balancing strategy
      server [HOST1]:[PORT];
      server [HOST1]:[PORT];
      keepalive 64;
    }

    server {
      listen 8080;
      client_max_body_size 1000M;
      large_client_header_buffers 4 32k;
      sendfile on;
      keepalive_timeout 0;
      location / {
        include uwsgi_params;
        uwsgi_pass backend;
      }
    }
    ```
    
    with nginx load balancing incoming requests, sending them to 2 caesar-rest http applications listening at `HOST1` and `HOST2` on port `PORT`.    
   
  - Create a `/etc/systemd/system/nginx.service` systemd file, e.g. see the example provided in the `config/nginx` directory:   
  
    ```
    [Unit]   
    Description=The NGINX HTTP and reverse proxy server  
    After=syslog.target network.target remote-fs.target nss-lookup.target caesar-rest.target   

    [Service]   
    Type=forking    
    PIDFile=/run/nginx.pid   
    ExecStartPre=/usr/sbin/nginx -t   
    ExecStart=/usr/sbin/nginx   
    ExecReload=/usr/sbin/nginx -s reload   
    ExecStop=/bin/kill -s QUIT $MAINPID   
    PrivateTmp=true    

    [Install]   
    WantedBy=multi-user.target   
    ```
  
  - Run nginx server:   

    ```sudo systemctl start nginx.service```

  Alternatively you can use the Docker container `sriggi/caesar-rest-lb:latest` (see https://hub.docker.com/r/sriggi/caesar-rest-lb) and deploy it with DockerCompose. In Kubernetes this functionality is provided by ingresses (see sample configuration files).   


