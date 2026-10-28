# Application discovery REST API

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 1559–1749). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

### **App list**
To get the list of supported apps:   

* URL:```http://server-address:port/caesar/api/v1.0/apps```   
* Request methods: GET   
* Request header: none

Server response contains a list of valid apps that can be queried for further description and used in job submission:    

```
{
  "apps": [
    "caesar",
    "mrcnn",
    "aegean",
    "cutex",
    "classifier-cnn",
    "classifier-vit",
    "featextractor-simclr",
    "umap",
    "outlier-finder",
    "hdbscan",
    "similarity-search"	
  ]
}
```

### **App description**
To get information about a given app:  

* URL:```http://server-address:port/caesar/api/v1.0/app/[app_name]/describe```   
* Request methods: GET    
* Request header: none

Server response contains a list of app options that can be used in job submission. Below we report a description of the `umap` app (url: `http://server-address:port/caesar/api/v1.0/app/umap/describe`):   
```
{
	"datalist-key": {
		"advanced": 0,
		"category": "INPUT",
		"default": "data",
		"description": "Dictionary key name to be read in input datalist (default=data)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	},
	"mindist": {
		"advanced": 0,
		"category": "PROCESSING",
		"default": 0.1,
		"description": " Min dist UMAP parameter (default=0.1)",
		"enum": false,
		"mandatory": false,
		"max": 1.0,
		"min": 0.0,
		"subcategory": "",
		"type": "float"
	},
	"nfeats": {
		"advanced": 0,
		"category": "PROCESSING",
		"default": 2,
		"description": "Encoded data dim in UMAP (default=2)",
		"enum": false,
		"mandatory": false,
		"max": 512,
		"min": 2,
		"subcategory": "",
		"type": "int"
	},
	"nneighbors": {
		"advanced": 0,
		"category": "PROCESSING",
		"default": 15,
		"description": "N neighbors UMAP parameter (default=15)",
		"enum": false,
		"mandatory": false,
		"max": 10000,
		"min": 1,
		"subcategory": "",
		"type": "int"
	},
	"no-logredir": {
		"advanced": 0,
		"category": "RUN",
		"description": "Do not redirect logs to output file in script",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"no-save-ascii": {
		"advanced": 0,
		"category": "OUTPUT",
		"description": "Do not save output in ascii format",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"no-save-json": {
		"advanced": 0,
		"category": "OUTPUT",
		"description": "Do not save output in json format",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"no-save-model": {
		"advanced": 0,
		"category": "OUTPUT",
		"description": "Do not save model",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"normalize_minmax": {
		"advanced": 0,
		"category": "PREPROCESSING",
		"description": "Normalize each channel in range",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"outfile-sup": {
		"advanced": 0,
		"category": "OUTPUT",
		"default": "featdata_umap_sup.dat",
		"description": "Name of UMAP encoded data output file for supervised run in ascii format (default=featdata_umap_sup.dat)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	},
	"outfile-unsup": {
		"advanced": 0,
		"category": "OUTPUT",
		"default": "featdata_umap.dat",
		"description": "Name of UMAP encoded data output file in ascii format (default=featdata_umap.dat)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	},
	"outfile-unsup-json": {
		"advanced": 0,
		"category": "OUTPUT",
		"default": "featdata_umap.json",
		"description": "Name of UMAP encoded data output file in json format (default=featdata_umap.json)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	},
	"run-supervised": {
		"advanced": 0,
		"category": "RUN",
		"description": "Run UMAP also on labelled data alone (if available)",
		"enum": false,
		"mandatory": false,
		"subcategory": "",
		"type": "none"
	},
	"selcols": {
		"advanced": 0,
		"category": "INPUT",
		"default": "",
		"description": "Data column ids to be selected from input data, separated by commas (default=all columns)",
		"enum": false,
		"mandatory": false,
		"max": "",
		"min": "",
		"subcategory": "",
		"type": "str"
	}
}

```

