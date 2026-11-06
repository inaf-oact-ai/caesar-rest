# Vision Transformer image classifier (`classifier-vit`)

> This reference describes the application contract in the CAESAR-REST `devel` configurator. Actual applications and available options can be queried with `GET /caesar/api/v1.0/apps` and `GET /caesar/api/v1.0/app/{app_name}/describe`. Application registration does not guarantee that its execution container is installed on every deployment.

See [Application discovery API](../applications.md) and [Job submission API](../jobs.md).

## Purpose

Applies pretrained ViT- or ResNet-based classifiers to radio-astronomical images. Available classifier families include multilabel morphology tagging, source-centric radio morphology labels, and field-level anomaly / artefact / radio-galaxy detection.

## Inputs

**Supported scientific formats:** `fits`, `png`, `json`.

A single FITS/PNG image, or a JSON datalist of images. Source-centric models expect cutouts centered on individual objects; wider-field models expect a scene that can contain multiple sources. The `model` option selects these semantics.

## Outputs

| Output | Artifact contract |
| --- | --- |
| Classifier predictions | `catalog` — JSON file `classifier_results.json` |
| Logs | `log` — `*.log` |

The result contains the input entry metadata together with prediction fields such as `label_pred` and `prob_pred`.

Output products are conditional on the scientific execution options and the actual job run. Consult job output or run-specific artifacts rather than assuming all declared products exist.

## Limitations

- Classifies existing images; **does not perform source detection** or generate bounding boxes / segmentation masks.
- Accuracy depends on model, preprocessing, image dimensions, beam/noise properties and observing survey.
- Models were trained and tested on radio data; other domains may perform poorly.

## Supported options

The following names are taken from the current configurator. Defaults and accepted values should be checked with the live `describe` endpoint before submission.

| Option | Default | Purpose |
| --- | --- | --- |
| `model` | `smorphclass_multilabel` | Select pretrained classifier |
| `zscale` | `true` | Apply z-scale preprocessing |
| `zscale-contrast` | `0.25` | z-scale contrast |
| `norm-min` | `0.0` | Normalization minimum |
| `norm-max` | `1.0` | Normalization maximum |
| `no-logredir` | `false` | Disable script log redirection |

Supported model names: `smorphclass_multilabel`, `smorphclass_singlelabel_rgz`, `smorphclass_singlelabel_lotss`, `anomalyclass_singlelabel`, `artefactdet_singlelabel`, `radiogaldet_singlelabel`.

## Example

Illustrative request to `POST /caesar/api/v1.0/job` (provide valid accessible input identifiers and a bearer token when authentication is enabled):

```json
{
  "app": "classifier-vit",
  "data_inputs": {"data": "<IMAGE_UID>", "format": "uid"},
  "job_options": {
    "model": "smorphclass_multilabel",
    "zscale": true,
    "zscale-contrast": 0.25
  }
}
```

## Further guidance

The legacy tutorial illustrates this model family. Its example field `zscale_contrast` should be updated to the current option spelling `zscale-contrast` when used with this configurator.
