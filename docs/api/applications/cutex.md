# CuTEx

## Overview

**Application name:** `cutex`

CuTEx (Curvature Thresholding Extractor) is a compact-source extraction tool designed to identify compact emission structures in astronomical images using curvature-based detection and source fitting. In CAESAR-REST it is registered as an image-processing application and executed through `cutex_submitter.sh`.

The CAESAR-REST configurator exposes source-detection thresholds, a minimum source-cluster size, point-spread-function (PSF) sampling, and bounds used for fitted source sizes. This page describes the **CAESAR-REST integration**; it does not claim that all features of the upstream CuTEx package are exposed.

**Tool category:** `image`  
**Batch processing:** enabled by the configurator

## Inputs

The application accepts a single image input passed as `--inputfile` to the execution script. A FITS astronomical image is the intended scientific input, but the current configurator has not yet formally validated the underlying container's accepted image formats.

CAESAR-REST job requests reference the input through `data_inputs` (for example, using an uploaded file UUID or a registered dataset). The input-reference mechanism is distinct from the scientific file format.

The source image should contain sufficiently sampled compact emission features for meaningful curvature-based detection and fitting. The `npixpsf` option describes how many pixels sample the instrumental PSF.

## Supported options

The values below are taken from `caesar_rest/app_configurators/cutex.py` on the `devel` branch.

| Option | Type | Default | Accepted range | Description |
| --- | --- | --- | --- | --- |
| `seedthr` | float | `5.0` | 0–10000 | Detection threshold, expressed in units of sigma |
| `npixmin` | integer | `4` | 1–10000 | Minimum number of pixels required for a significant cluster |
| `npixpsf` | float | `2.7` | 1–10000 | Number of pixels sampling the instrumental PSF |
| `psflimmin` | float | `0.5` | 0.0001–100 | Lower bound on fitted source size relative to the initial size estimate |
| `psflimmax` | float | `2.0` | 0.0001–100 | Upper bound on fitted source size relative to the initial size estimate |
| `no-logredir` | flag | not explicitly set | — | Disable redirection of logs to a file |

The application automatically adds `--run`, `--save-summaryplot` and `--save-catalog-to-json` to its command arguments. These are execution-script flags, not user-supplied `job_options`.

For the deployment's definitive option description, query:

```http
GET /caesar/api/v1.0/app/cutex/describe
```

## Outputs

The command configuration requests a **summary plot** and **JSON catalog**, and the execution may produce diagnostic logs. However, `self.job_outputs` is currently empty: exact filenames, JSON structure, and whether each product is guaranteed have **not been verified** against the CuTEx container.

| Expected product | Purpose | Verification status |
| --- | --- | --- |
| Source catalog (JSON) | Record detected sources and fitted properties | Requested by `--save-catalog-to-json`; filename and schema unverified |
| Summary plot | Visual inspection of detections | Requested by `--save-summaryplot`; filename unverified |
| Execution log | Diagnostics and troubleshooting | Depends on script behavior and log redirection |

Until output paths are confirmed, the job archive should be inspected directly. Do not assume the same filename conventions or source-catalog schema used by CAESAR or Aegean.

## Example: source extraction from an uploaded FITS image

Submit to:

```http
POST /caesar/api/v1.0/job
```

Example request payload (replace the placeholder UUID with an accessible uploaded file identifier):

```json
{
  "app": "cutex",
  "data_inputs": {
    "data": "UPLOADED_FITS_FILE_UUID",
    "format": "uid"
  },
  "job_options": {
    "seedthr": 5.0,
    "npixmin": 4,
    "npixpsf": 2.7,
    "psflimmin": 0.5,
    "psflimmax": 2.0
  }
}
```

The request follows the standard CAESAR-REST job submission contract. After submission, use the returned `job_id` to monitor and retrieve the results:

```http
GET /caesar/api/v1.0/job/{job_id}/status
GET /caesar/api/v1.0/job/{job_id}/output
```

See [Job submission and monitoring](../jobs.md) for authentication and response details.

## Limitations

- Detection completeness and false-positive rates depend on image noise, source crowding and the selected curvature/detection threshold.
- Fitting quality depends on instrumental PSF sampling and the chosen bounds on source size.
- Very extended, diffuse emission is not necessarily well described by a compact-source extraction workflow.
- The configurator does not currently expose a complete, machine-readable output contract; clients should inspect actual job results before assuming a specific output product or parser.
- Scientific input-format support and output filenames need verification against the deployed container.

## References

- [CAESAR-REST application discovery API](../applications.md)
- [CAESAR-REST job submission API](../jobs.md)
- [CAESAR-REST source configurator](https://github.com/inaf-oact-ai/caesar-rest/blob/devel/caesar_rest/app_configurators/cutex.py)
