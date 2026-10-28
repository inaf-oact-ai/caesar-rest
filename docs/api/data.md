# Data and datasets REST API

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 1469–1558). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

### **Data upload**

* URL:```http://server-address:port/caesar/api/v1.0/upload```   
* Request methods: POST   
* Request header: ```content-type: multipart/form-data```   

A sample curl request would be:   

```
curl -X POST \   
  -H 'Content-Type: multipart/form-data' \   
  -F 'file=@VGPS_cont_MOS017.fits' \   
  --url 'http://localhost:8080/caesar/api/v1.0/upload'   
```

Server response is:   
```
{
  "date":"2020-04-24T17:04:26.174333",
  "filename_orig":"VGPS_cont_MOS017.fits",
  "format":"fits",
  "size":4.00726318359375,
  "status":"File uploaded with success",
  "uuid":"250fdf5ed6a044888cf4406338f9e73b"
}
```

A file uuid (or file path) are returned and can be used to download the file or set job input file information.   

### **Data download**

* URL:```http://server-address:port/caesar/api/v1.0/download/[file_id]```   
* Request methods: GET, POST   
* Request header: None  

A sample curl request would be:   

```
curl  -X GET \
  --fail -o data.fits \
  --url 'http://localhost:8080/caesar/api/v1.0/download/67a49bf7555b41739095681bf52a1f99'
```

The above request will fail if file is not found, otherwise the downloaded file will be saves as `data.fits`. Without the `-o` argument raw output is written to stdout. If file is not found a json response is returned:   

```
{
  "status": "File with uuid 67a49bf7555b41739095681bf52a1f99 not found on the system!"
}
```

### **Get uploaded data ids**

* URL:```http://server-address:port/caesar/api/v1.0/fileids```   
* Request methods: GET   
* Request header: None  

A sample curl request would be:   

```
curl  -X GET \
  --url 'http://localhost:8080/caesar/api/v1.0/fileids'
```

with response:    

```
{"file_ids":["a668c353ba4d4c7395ad94b4e8647d92","c54db5ef95734c62a499db38587c48a5","26bc9a545c8f4f05a2c719ec5c3917e0"]}
```

### **Dataset list & description**
To get the list of supported datasets: 

* URL:```http://server-address:port/caesar/api/v1.0/datasets```   
* Request methods: GET   
* Request header: none

Server response contains a list of configured datasets that can be used as inputs in job submission:   

```
{
  "smgps": {
    "description": "A collection of 178,057 image cutouts of size 256x256 pixels extracted from the SARAO MeerKAT Galactic Plane survey (Goedhart+24)."
  },
  "smgps-feats-simclr": {
    "description": "Feature data (#512 features) obtained with a SimCLR self-supervised pre-trained model from a collection of 178,057 image cutouts of size 256x256 pixels extracted from the SARAO MeerKAT Galactic Plane survey (Goedhart+24)."
  }
}
```

