# CAESAR-YOLO

**Application identifier:** `caesar-yolo`  
**Category:** Radio-source object detection and morphological classification  
**Configurator:** `caesar_rest/app_configurators/caesar_yolo.py`

## Purpose

CAESAR-YOLO applies pretrained YOLO models to radio-continuum images to detect candidate objects and assign morphological classes. Unlike image-only classification, it produces localized detections, including bounding-box information and confidence scores. The model and preprocessing affect both detection and classification quality.

## Input requirements

- **Scientific formats:** FITS or PNG radio-continuum image.
- **Quantity:** One image per ordinary job.
- Large images should be processed using the app's supported tiling mode.

## Outputs

| Logical output | Default or pattern | Content |
| --- | --- | --- |
| `catalog` | `catalog.json` (`*.json`) | JSON catalog of detected, classified objects |
| `plot` | `plot.png` (`*.png`) | Optional visualization of detections |
| `region` | `ds9.reg` (`*.reg`) | Optional DS9 boxes with tags/classes |
| `log` | `*.log` | Execution diagnostics |

Default output filenames are configurable through `outfile-catalog`, `outfile-plot` and `outfile-region`. The catalog is declared as the primary result. Optional visualization files may not be produced in every run.

## Supported options

The current configurator defines options in the following functional groups:

| Group | Notable options | Meaning |
| --- | --- | --- |
| Model | `model`, `imgsize`, `nchans` | Select pretrained model and image dimensions/channels |
| Input crop | `xmin`, `xmax`, `ymin`, `ymax` | Restrict input pixel region |
| Normalization | `preprocessing`, `normalize`, `norm-min`, `norm-max`, `zscale`, `zscale-contrasts` | Control image preparation |
| Background/clipping | `subtract-bkg`, `sigma-bkg`, `clipdata`, `sigmaclip-low`, `sigmaclip-up`, `chan3-preproc` | Optional preprocessing variants |
| Detection | `score-thr`, `iou-thr`, `merge-overlap-iou-thr-soft`, `merge-overlap-iou-thr-hard` | Detection filtering and overlap handling |
| Tiling | `split-img-in-tiles`, `tile-xsize`, `tile-ysize`, `tile-xstep`, `tile-ystep`, `max-ntasks-per-worker` | Large-image processing |
| Outputs | `draw-plots`, `save-plots`, `outfile-plot`, `outfile-catalog`, `outfile-region` | Output production and naming |
| Runtime | `no-logredir` | Execution logging |

Selected configurator defaults: `model=yolov11l_imgsize640`, `imgsize=640`, `score-thr=0.5`, `iou-thr=0.5`, `zscale=true`, `split-img-in-tiles=false`. See `GET /caesar/api/v1.0/app/caesar-yolo/describe` for the full option list, allowed values and bounds.

## Limitations

- Source detection is sensitive to model choice, input resolution and noise, preprocessing, score threshold and IoU threshold.
- Use the image size associated with the pretrained model; selecting the input image's original size indiscriminately is not recommended.
- Images larger than the model input field require appropriate tiling and parallel processing for complete coverage.
- Models were trained and evaluated on radio images; equivalent performance on other imaging domains has not been demonstrated.

## Example: detecting radio sources

```http
POST /caesar/api/v1.0/job
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "app": "caesar-yolo",
  "data_inputs": {
    "data": "<registered-fits-file-id>",
    "format": "uid"
  },
  "job_options": {
    "model": "yolov11l_imgsize640",
    "imgsize": 640,
    "score-thr": 0.5,
    "iou-thr": 0.5,
    "outfile-catalog": "catalog.json"
  }
}
```

Use an accessible registered image identifier. Model availability depends on the installed scientific container; this example has not been executed against the live deployment. See the [jobs API](../jobs.md) for monitoring and output retrieval.
