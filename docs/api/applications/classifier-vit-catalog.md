# Vision Transformer catalog classifier (`classifier-vit-catalog`)

> This reference describes the application contract in the CAESAR-REST `devel` configurator. Actual applications and available options can be queried with `GET /caesar/api/v1.0/apps` and `GET /caesar/api/v1.0/app/{app_name}/describe`. Application registration does not guarantee that its execution container is installed on every deployment.

See [Application discovery API](../applications.md) and [Job submission API](../jobs.md).

## Purpose

Enriches a radio-source catalog with model predictions. It extracts a cutout around each cataloged object from the associated radio image and classifies those cutouts with a source-centric pretrained model. The source-finding catalog is preserved and enhanced, rather than producing a separate full-image classification.

## Inputs

**Supported scientific formats:** Image: `fits`, `png`, `jpg`, `jpeg`; catalog: `json`.

**Exactly two ordered inputs are required:** (1) image file, then (2) source catalog JSON associated with that image. The catalog must use the same image pixel coordinate frame. Caesar, Aegean and Caesar-YOLO or compatible catalogs are supported by the configurator's intended contract.

## Outputs

- `catalog`: enhanced source catalog in JSON, containing original source properties plus model classifications.
- `log`: diagnostic execution logs.

Output products are conditional on the scientific execution options and the actual job run. Consult job output or run-specific artifacts rather than assuming all declared products exist.

## Limitations

- Does not detect sources; only processes detections already in the input catalog.
- Cutouts are generated in image pixel coordinates, so catalog/image spatial consistency is mandatory.
- Prediction quality depends on catalog reliability, cutout sizing, source extent, instrument resolution and classifier model.

## Supported options

The following names are taken from the current configurator. Defaults and accepted values should be checked with the live `describe` endpoint before submission.

| Option | Default | Meaning |
| --- | --- | --- |
| `model` | `smorphclass_singlelabel_rgz` | `smorphclass_singlelabel_rgz` or `smorphclass_singlelabel_lotss` |
| `catalog-level` | `auto` | `auto`, `source`, `island`, `component` |
| `size-mode` | `bbox_factor` | `bbox` or `bbox_factor` |
| `cutout-size` | `32` | Minimum pixel size |
| `cutout-margin` | `0` | Extra source-box margin in pixels |
| `cutout-margin-factor` | `1.2` | Bounding box scale factor |
| `overwrite-class-fields` | `false` | Allow replacing existing classification fields |
| `zscale` | `true` | Image contrast preprocessing |
| `zscale-contrast` | `0.25` | z-scale contrast |
| `norm-min` | `0.0` | Normalization minimum |
| `norm-max` | `1.0` | Normalization maximum |
| `no-logredir` | `false` | Disable script log redirection |

## Example

Illustrative request to `POST /caesar/api/v1.0/job` (provide valid accessible input identifiers and a bearer token when authentication is enabled):

```json
{
  "app": "classifier-vit-catalog",
  "data_inputs": {
    "data": ["<IMAGE_UID>", "<SOURCE_CATALOG_UID>"],
    "format": ["uid", "uid"]
  },
  "job_options": {
    "model": "smorphclass_singlelabel_rgz",
    "catalog-level": "auto",
    "size-mode": "bbox_factor",
    "cutout-margin-factor": 1.2
  }
}
```

## Further guidance

This application is distinct from `classifier-vit`, which accepts images or image datalists and produces image-level predictions.
