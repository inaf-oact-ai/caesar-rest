# Fextractor scientific embeddings (`fextractor`)

> This reference describes the application contract in the CAESAR-REST `devel` configurator. Actual applications and available options can be queried with `GET /caesar/api/v1.0/apps` and `GET /caesar/api/v1.0/app/{app_name}/describe`. Application registration does not guarantee that its execution container is installed on every deployment.

See [Application discovery API](../applications.md) and [Job submission API](../jobs.md).

## Purpose

Extracts fixed-dimensional scientific representations using pretrained foundation models or statistical feature extractors. The configurator supports **images** and **time series**, including irregularly sampled multichannel light curves when the selected backend supports them.

## Inputs

**Supported scientific formats:** `fits`, `png`, `jpg`, `jpeg`, `csv`, `ecsv`, `npy`, `npz`, `json`.

Image inputs may be files or JSON datalists. Time-series inputs may be long-format CSV/ECSV (explicit time column, one or more value columns and optional errors), wide-format tabular inputs, NumPy arrays or JSON datalists. Use the corresponding `timeseries-*`, `time-*`, `value-*` and `error-*` options. Irregular sampling can require explicit timestamps and configured regularization depending on the model.

## Outputs

| Output | Description |
| --- | --- |
| `embeddings-json` | `*.json`, default `fextractor_results.json`, configurable with `outfile`; fixed-size features / embeddings and sample metadata |
| `timeseries-plot` | `*_timeseries.png` diagnostic visualization, when enabled |
| `log` | `*.log` execution diagnostics |

Output products are conditional on the scientific execution options and the actual job run. Consult job output or run-specific artifacts rather than assuming all declared products exist.

## Limitations

- Preprocessing and model options depend strongly on image vs. time-series modality.
- Chronos-2 and Falcon-1 need regular cadence unless regularization is enabled.
- Falcon-1 handles multiple channels independently, without explicit cross-channel relationships.
- LiCu handcrafted features and some single-channel embedding models also process each channel independently; AstraCLR, ATAT and ATCAT support native multiband observations.
- `aggregation`, `context-length`, `batch-size` and patching controls are not universally supported; use only with compatible models.
- Missing data, uncertainty representations and interpolation can alter extracted features.

## Supported options

The following names are taken from the current configurator. Defaults and accepted values should be checked with the live `describe` endpoint before submission.

The configurator defines more than 50 options. Core groups are summarized below. All names in these groups are literal configuration keys.

| Group | Options |
| --- | --- |
| Model and execution | `model`, `device`, `batch-size`, `skip-errors`, `no-logredir`, `nmax`, `outfile` |
| Image preprocessing | `preproc-profile`, `norm-min`, `norm-max`, `imgsize`, `nchannels`, `clipdata`, `zscale`, `zscale-contrast`, `set-zero-to-min`, `reset-meanstd`, `reset-rescale` |
| Datalist parsing | `datalist-key`, `timeseries-layout`, `time-column`, `value-columns`, `error-columns`, `band-column`, `value-prefixes`, `error-prefixes`, `time-prefix`, `time-start-column`, `cadence-column`, `channel-names`, `label-column`, `metadata-columns`, `time-start-key`, `cadence-key`, `band-key` |
| Resampling | `regularize`, `cadence`, `missing-strategy`, `regularization-method`, `bin-aggregation`, `gp-sigma`, `gp-rho`, `gp-jitter`, `input-sample-policy` |
| Representation | `aggregation`, `context-length`, `patching-mode`, `token-order`, `timeseries-plot` |
| Statistical and LiCu features | `feature-set`, `invalid-feature-policy`, `min-samples`, `licu-embed-output`, `licu-embed-reduction`, `licu-mag-zp`, `licu-allow-extra-bands` |

Common `model` values include image models `simclr_radio`, `dinov2`, `dinov3`, `siglip`, `siglip2`; time-series foundation models `chronos2`, `moirai2`, `falcon1`; and statistical / LiCu-related backends. **The live enumeration is authoritative**, including exact supported model names.

The default `model` in `devel` is `simclr_radio`; the default `outfile` is `fextractor_results.json`.

## Example

Illustrative request to `POST /caesar/api/v1.0/job` (provide valid accessible input identifiers and a bearer token when authentication is enabled):

```json
{
  "app": "fextractor",
  "data_inputs": {"data": "<FITS_IMAGE_UID>", "format": "uid"},
  "job_options": {
    "model": "simclr_radio",
    "outfile": "fextractor_results.json",
    "device": "cuda"
  }
}
```

## Further guidance

For a light-curve job, choose a time-series model such as `chronos2` and supply the parsing, cadence and optional regularization settings compatible with the actual dataset. No single example can cover all model backends.
