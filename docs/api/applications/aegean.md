# Aegean

**Application identifier:** `aegean`  
**Category:** Radio-continuum image source finding  
**Configurator:** `caesar_rest/app_configurators/aegean.py`

## Purpose

Aegean detects compact and point-like radio sources in astronomical images, estimates source properties, and characterizes individual fitted Gaussian components. It uses image background/noise estimates and flood-fill detection thresholds.

## Input requirements

- **Scientific format:** FITS radio-continuum image.
- **Quantity:** One image per ordinary job.
- Supply an accessible data reference through the standard CAESAR-REST `data_inputs` payload; `uid` and `dataset` identify registered inputs, not distinct image formats.

## Outputs

The configurator declares the following products. Output availability depends on job completion and configured behavior.

| Logical output | Filename pattern | Content |
| --- | --- | --- |
| `catalog_json` | `catalog-*.json` | Source catalog (primary result) |
| `catalog_ascii` | `catalog-*_isle.tab` | Island-level tabular catalog |
| `catalog_components_ascii` | `catalog-*_comp.tab` | Gaussian-component table |
| `plot` | `plot_*.png` | Source detections displayed on an image |
| `region` | `ds9-*_isle.reg` | DS9 source-island regions |
| `region_components` | `ds9-*_comp.reg` | DS9 fitted-component ellipses |
| `log` | `*.log` | Execution diagnostics |

The configurator enables summary plots, DS9 regions and JSON catalog generation by default when constructing its command.

## Supported options

| Option | Default | Purpose |
| --- | --- | --- |
| `save-bkgmap` | `false` | Save estimated background map |
| `save-rmsmap` | `false` | Save local RMS map |
| `bkgbox` | `100` | Local-background box size in pixels |
| `bkggrid` | `20` | Background-sampling grid size in pixels |
| `seedthr` | `5` | Detection seed threshold in sigma |
| `mergethr` | `2.6` | Flood-fill merge threshold in sigma |
| `fit-maxcomponents` | `3` | Maximum fitted components per island |
| `ncores` | `1` | Processing cores used by BANE/Aegean |
| `no-logredir` | `false` | Disable log redirection |

For live option types, bounds and validation, use `GET /caesar/api/v1.0/app/aegean/describe`.

## Limitations

- Detection accuracy depends on noise/background estimation and thresholds.
- Very large images (e.g. beyond 10,000 pixels across) may be expensive. The configurator does not advertise an image-tiling parallel mode, although it has an `ncores` setting for underlying tools.
- It was developed and tested for radio images; use on other astronomical bands is not established to give comparable results.

## Example: source finding on a registered image

```http
POST /caesar/api/v1.0/job
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "app": "aegean",
  "data_inputs": {
    "data": "<registered-fits-file-id>",
    "format": "uid"
  },
  "job_options": {
    "seedthr": 5,
    "mergethr": 2.6,
    "fit-maxcomponents": 3,
    "ncores": 1
  }
}
```

The file identifier is a placeholder; substitute an accessible uploaded or registered FITS image. Retrieve the job ID from the submission response and use the [jobs API](../jobs.md) to monitor and download outputs.
