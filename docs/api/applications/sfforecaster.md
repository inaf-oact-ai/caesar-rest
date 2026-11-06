# Solar flare forecaster (`sfforecaster`)

> This reference describes the application contract in the CAESAR-REST `devel` configurator. Actual applications and available options can be queried with `GET /caesar/api/v1.0/apps` and `GET /caesar/api/v1.0/app/{app_name}/describe`. Application registration does not guarantee that its execution container is installed on every deployment.

See [Application discovery API](../applications.md) and [Job submission API](../jobs.md).

## Purpose

Runs pretrained transformer-based models to forecast whether an M-class or stronger solar flare will occur within the following 24 hours. Models are tailored to individual magnetogram images, sequences of magnetogram frames, or regularly sampled solar time series.

## Inputs

**Supported scientific formats:** `fits`, `png`, `json`, `csv`.

Input depends on the selected model: one solar-active-region magnetogram (FITS/PNG), a sequence of magnetograms, a CSV time series, or a JSON datalist describing such inputs. Image models expect active-region crops, **not full-disk images**. Video models expect 16 frames at 36- or 72-minute cadence; the time-series model is configured for 1,440 steps at 1-minute cadence.

## Outputs

| Output | Contract |
| --- | --- |
| Solar-flare predictions | `catalog` — `classifier_results.json` |
| Diagnostic logs | `log` — `*.log` |

The primary result is a JSON catalog of predicted flare classes / scores; inspect the output schema in the live configurator and the concrete execution result.

Output products are conditional on the scientific execution options and the actual job run. Consult job output or run-specific artifacts rather than assuming all declared products exist.

## Limitations

- Forecasts M+ flares; it **does not detect active regions** or forecast solar energetic particle events.
- Full-disk data are not currently supported by the pretrained forecasting models.
- Models are optimized for active-region magnetograms; alternative solar imagery may perform poorly.
- Skill depends on training domain, preprocessing, temporal sampling and selected model.

## Supported options

The following names are taken from the current configurator. Defaults and accepted values should be checked with the live `describe` endpoint before submission.

| Option | Default | Purpose |
| --- | --- | --- |
| `model` | `image_M+24h` | Input modality / temporal model |
| `binary-thr` | `0.5` | Positive class decision threshold |
| `zscale` | `true` | Image z-scale preprocessing |
| `zscale-contrast` | `0.25` | Contrast for image inputs |
| `no-logredir` | `false` | Disable log redirection |

Accepted models: `image_M+24h`, `video_n16_dt36m_M+24h`, `video_n16_dt72m_M+24h`, `ts_n1440_dt1m_M+24h`.

## Example

Illustrative request to `POST /caesar/api/v1.0/job` (provide valid accessible input identifiers and a bearer token when authentication is enabled):

```json
{
  "app": "sfforecaster",
  "data_inputs": {"data": "<ACTIVE_REGION_FITS_UID>", "format": "uid"},
  "job_options": {
    "model": "image_M+24h",
    "binary-thr": 0.5,
    "zscale": true
  }
}
```

## Further guidance

The selected model determines whether image, video or time-series inputs are valid. This example uses the single-image model.
