# UMAP

UMAP performs nonlinear dimensionality reduction, mapping observations from a high-dimensional feature space into a smaller representation suitable for visualization and exploratory analysis.

**Registered app:** `umap`  
**Category:** `tabular`  
**Configurator:** [`caesar_rest/app_configurators/umap.py`](https://github.com/inaf-oact-ai/caesar-rest/blob/devel/caesar_rest/app_configurators/umap.py)

## Scientific purpose

UMAP performs nonlinear dimensionality reduction, mapping observations from a high-dimensional feature space into a smaller representation suitable for visualization and exploratory analysis. Results can be used in subsequent exploratory workflows; they are not themselves an automatic scientific validation of labels or classes.

## Input data

Supported scientific input formats are **JSON** and **ASCII** tabular feature data. JSON inputs contain a top-level `data` array with an entry per observation; `feats` is a numeric feature vector. Entries can include `sname`, `id`, `label`, and other metadata, which the application can preserve in JSON output.

```json
{
  "data": [
    {"sname": "source-001", "id": 2, "label": "EXTENDED", "feats": [0.96, 2.24, 0.0, 0.59]},
    {"sname": "source-002", "id": 1, "label": "COMPACT", "feats": [0.14, 0.31, 0.8, 0.47]}
  ]
}
```

For ASCII input, the first column identifies the observation, subsequent columns contain feature values, and an optional final column contains a class ID or label. The `data_inputs` object of a job request identifies an uploaded file or registered dataset; this is distinct from the scientific file format described here. See [Data API](../data.md) and [Jobs API](../jobs.md).


## Outputs

The configurator declares the following scientific output families. Files actually produced depend on selected options and container execution:

- **`embeddings-json`** — JSON embedding data, including new feature vectors; default unsupervised filename: `featdata_umap.json` (configurable with `outfile-unsup-json`).
- **`embeddings-ascii`** — ASCII embedded features (`*.dat`).
- **`embeddings-ascii-supervised`** — Additional supervised embedding when enabled and labelled data are available.
- **`datascaler`** — Feature scaling information, if produced.
- **`model`** — Saved UMAP model, unless disabled.
- **`log`** — Execution log.

Output products are retrieved from the job output archive for ordinary jobs. For pipeline runs, consult the run-specific artifact inventory; a declared output is not proof of availability in an individual run.

## Supported options

The following options are declared in the `devel` application configurator. Defaults and types should be checked with the live `GET /app/umap/describe` response for the installed version.

| Option | Type | Default | Purpose |
| --- | --- | --- | --- |
| `datalist-key` | str | `data` | Top-level JSON array key |
| `selcols` | str | `empty` | Dash-separated feature-column indices |
| `nfeats` | int | `2` | Output embedding dimensions |
| `mindist` | float | `0.1` | Minimum distance / embedding compactness |
| `nneighbors` | int | `15` | Neighborhood size |
| `normalize` | bool | `true` | Normalize feature data to [0,1] |
| `ids-excluded-in-train` | str | `-1:0` | Class identifiers excluded from supervised training |
| `run-supervised` | bool | `false` | Also run on labelled examples |
| `no-save-ascii` | bool | `false` | Disable ASCII outputs |
| `no-save-json` | bool | `false` | Disable JSON outputs |
| `no-save-model` | bool | `false` | Disable model saving |
| `outfile-sup` | str | `featdata_umap_sup.dat` | Supervised ASCII filename |
| `outfile-unsup` | str | `featdata_umap.dat` | Unsupervised ASCII filename |
| `outfile-unsup-json` | str | `featdata_umap.json` | Unsupervised JSON filename option |
| `no-logredir` | bool | `false` | Disable log redirection |

## Example: submit a job

This example assumes `smgps-feats-simclr` is registered and accessible in the deployment. Replace it with an available dataset as needed.

```bash
curl --fail-with-body -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data-binary @payload.json \
  "${BASE_URL}/caesar/api/v1.0/job"
```

`payload.json`:

```json
{
  "app": "umap",
  "data_inputs": {
    "data": "smgps-feats-simclr",
    "format": "dataset"
  },
  "job_options": {
    "nfeats": 2,
    "mindist": 0.1,
    "nneighbors": 20,
    "normalize": true,
    "run-supervised": false,
    "no-save-ascii": true,
    "no-save-model": true
  }
}
```

The server returns a `job_id` that can be used for status monitoring and output retrieval. See [Jobs API](../jobs.md) for those endpoints. The request is a legacy single-job example, not a Pipeline V2 run-registration request.

## Limitations and interpretation

- The embedding is sensitive to `nneighbors` and `mindist`; different settings can change the apparent cluster structure.
- A UMAP embedding is an exploratory representation; visual separation alone does not establish a scientifically validated class.

Execution time depends on dataset size, dimensionality, backend and container resources; historical timings should not be treated as current service guarantees.

## References

- [Application discovery REST API](../applications.md)
- [Job submission API](../jobs.md)
- [Historical CAESAR-REST tutorial (examples; may use superseded option names)](https://github.com/SKA-INAF/caesar-rest)
