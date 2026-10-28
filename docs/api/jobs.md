# Jobs REST API

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 1750–1840). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

### **Job submission**
* URL:```http://server-address:port/caesar/api/v1.0/job```   
* Request methods: POST   
* Request header: ```content-type: application/json```   

A sample curl request for running the `caesar` source finder app would be:   

```
curl -X POST \   
  -H 'Content-Type: application/json' \   
  -d '{"app": "caesar","data_inputs": {"data": "39ca08fc5c7c446d8756a48088ee684c"},"job_options": {"run": true,"no-logredir": true,"no-mpi": true,"no-nestedsearch": true,"no-extendedsearch": true}}' \   
  --url 'http://localhost:8080/caesar/api/v1.0/job'   
```

Job data must contain a valid app name (in this case `caesar`) and desired job inputs, e.g. a dictionary with app valid options. Valid options for `caesar` app are named as in `caesar` and can be retrieved using app description url described above.   

Server response is:   

```
{
  "app": "caesar",
  "data_inputs": "39ca08fc5c7c446d8756a48088ee684c",
  "job_id": "a4095b815a074d81a0cc447762aa29f1",
  "job_options": {
    "no-extendedsearch": true,
    "no-logredir": true,
    "no-mpi": true,
    "no-nestedsearch": true,
    "run": true
   },
   "state": "PENDING",
   "status": "Job submitted and registered with success",
   "submit_date": "2024-12-19T10:00:42.865802",
   "tag": ""
}
```

A job id is returned in the response which can be used to query the status of the job or cancel it or retrieve output data at completion. 

### **Get job status**
* URL:```http://server-address:port/caesar/api/v1.0/job/[job_id]/status```   
* Request methods: GET   
* Request header: None   

A sample curl request would be:   

```
curl -X GET \   
  --url 'http://localhost:8080/caesar/api/v1.0/job/f135bcee-562b-4f01-ad9b-103c35b13b36/status'   
```

Server response is:   

```
{
  "elapsed_time": "27.3435878754",
  "exit_status": 0,
  "job_id": "f135bcee-562b-4f01-ad9b-103c35b13b36",
  "pid": "11539",
  "state": "SUCCESS",
  "status": "Process terminated with success"
}
```

Exit status is the shell exit status of background task executed and pid the corresponding process id. Possible job states are: {STARTED, TIMED-OUT, ABORTED, RUNNING, SUCCESS, FAILURE}. 


### **Get job output**
* URL:```http://server-address:port/caesar/api/v1.0/job/[job_id]/output```   
* Request methods: GET   
* Request header: None   

A sample curl request would be:   

```
curl -X GET \   
  --fail -o job_output.tar.gz \
  --url 'http://localhost:8080/caesar/api/v1.0/job/c3c9348a-bea0-4141-8fe9-7f64076a2327/output'   
```

The response is a tar.gz file containing all job directory files (logs, output data, run scripts, etc).  

### **Cancel job**
* URL:```http://server-address:port/caesar/api/v1.0/job/[job_id]/cancel```   
* Request methods: POST   
* Request header: None  

### **Get job ids**
* URL:```http://server-address:port/caesar/api/v1.0/jobs```   
* Request methods: GET   
* Request header: None  
