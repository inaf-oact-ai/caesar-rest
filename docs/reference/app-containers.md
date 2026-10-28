# Application container images

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 99–133). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

### **App containers**
Apps are run as Docker (Kuberneter deploy) or Singularity (Slurm deploy) containers. Docker images are available in DockerHub:   

* `caesar` source finder job: `docker://sriggi/caesar-job`   
* `caesar-yolo` radio source finder based on YOLO object detector: `docker://sriggi/caesar-yolo-job`  
* `aegean` source finder job: `docker://sriggi/aegean-job`
* `cutex` source finder job: `docker://sriggi/cutex-job`
* `mrcnn` object detector (TensorFlow 1.x): `docker://sriggi/mrcnn-detect`
* `classifier-cnn` CNN image classifier (TensorFlow 2.x): `docker://sriggi/cnn-classifier`
* `classifier-vit` ViT image classifier (PyTorch 2.x + Transformers): `docker://sriggi/vit-classifier`
* `umap` dimensionality reduction: `docker://sriggi/umap-job`  
* `outlier-finder` with Isolation Forest: `docker://sriggi/outlier-finder-job`   
* `hdbscan` cluster search: `docker://sriggi/hdbscan-job`
* `similarity-search`: image similarity search: `docker://sriggi/similarity-search-job`   
* `sfforecaster`: solar flare forecasting with pre-trained foundation models: `sriggi/sfforecaster-job`  
* `fextractor`: image/light-curve feature extractor with pre-trained foundation models:    
			- TensorFlow ResNet image models: `sriggi/fextractor-tf`    
			- PyTorch ResNet/ViT image models: `sriggi/fextractor-torch`   
			- Google Chronos2 timeseries model: `sriggi/fextractor-chronos`   
			- Moirai2 timeseries model: `sriggi/fextractor-moirai`  
			- FATS timeseries library: `sriggi/fextractor-fats`  
			- LiCU timeseries library & models: `sriggi/fextractor-licu`    
			- Falcon timeseries model: `sriggi/fextractor-falcon`   

Singularity containers can be created from docker images with:   

```singularity pull [DOCKER URL]```

Try to change these Singularity environment variables in case you don't have enough disk space for building the containers in the Singularity default cache/tmp directories:   

```SINGULARITY_CACHEDIR```    
```SINGULARITY_TMPDIR```    

**NB: You may experience this error when running Singularity containers that produces large outputs (e.g. hundreds or MB or more): `OSError: [Errno 28] No space left on device`. Try to increase the default value (64 MB) of the `sessiondir max size` parameter in Singularity configuration file `/usr/local/etc/singularity/singularity.conf`.**      

