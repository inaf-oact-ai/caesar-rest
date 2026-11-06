# HDBSCAN

HDBSCAN performs density-based clustering on feature tables, identifying dense groups of observations and points that do not belong to a cluster.

**Registered app:** `hdbscan`  
**Category:** `tabular`  
**Configurator:** [`caesar_rest/app_configurators/hdbscan.py`](https://github.com/inaf-oact-ai/caesar-rest/blob/devel/caesar_rest/app_configurators/hdbscan.py)

## Scientific purpose

HDBSCAN performs density-based clustering on feature tables, identifying dense groups of observations and points that do not belong to a cluster. Results can be used in subsequent exploratory workflows; they are not themselves an automatic scientific validation of labels or classes.

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

- **`clusters-json`** — JSON output (`clustered_data.json` by default) preserving input metadata and adding `clust_id`, `clust_prob`, `clust_outlier_score`. A cluster ID of -1 identifies noise.
- **`clusters-ascii`** — ASCII clustered data (`clustered_data.dat` by default).
- **`datascaler`** — Data scaler, when produced.
- **`model`** — Cluster model, unless disabled.
- **`log`** — Execution log.

Output products are retrieved from the job output archive for ordinary jobs. For pipeline runs, consult the run-specific artifact inventory; a declared output is not proof of availability in an individual run.

## Supported options

The following options are declared in the `devel` application configurator. Defaults and types should be checked with the live `GET /app/hdbscan/describe` response for the installed version.

| Option | Type | Default | Purpose |
| --- | --- | --- | --- |
| `datalist-key` | str | `data` | JSON data key |
| `selcols` | str | `empty` | Dash-separated feature-column indices |
| `min-cluster-size` | int | `5` | Minimum points in a cluster |
| `min-samples` | int | `-1` | Minimum samples; negative means infer from cluster size |
| `cluster-selection-epsilon` | float | `0` | Cluster merge distance threshold |
| `normalize` | bool | `true` | Normalize features |
| `reduce-dim` | bool | `false` | Apply dimensionality reduction before clustering |
| `reduce-dim-method` | str | `pca` | Reduction method |
| `pca-ncomps` | int | `-1` | PCA component count, or variance-based choice |
| `pca-varthr` | float | `0.9` | PCA retained variance threshold |
| `no-save-ascii` | bool | `false` | Disable ASCII |
| `no-save-json` | bool | `false` | Disable JSON |
| `no-save-model` | bool | `false` | Disable model |
| `no-save-features` | bool | `false` | Omit features from outputs |
| `outfile` | str | `clustered_data.dat` | ASCII output filename |
| `outfile-json` | str | `clustered_data.json` | JSON output filename |
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
  "app": "hdbscan",
  "data_inputs": {
    "data": "smgps-feats-simclr",
    "format": "dataset"
  },
  "job_options": {
    "min-cluster-size": 5,
    "min-samples": -1,
    "cluster-selection-epsilon": 0.0,
    "normalize": true,
    "no-save-ascii": true,
    "no-save-model": true
  }
}
```

The server returns a `job_id` that can be used for status monitoring and output retrieval. See [Jobs API](../jobs.md) for those endpoints. The request is a legacy single-job example, not a Pipeline V2 run-registration request.

## Limitations and interpretation

- Clusters depend on `min-cluster-size`, `min-samples`, and `cluster-selection-epsilon`.
- Clustering in very high dimensions may be ineffective; dimensionality reduction with PCA or UMAP can help.

Execution time depends on dataset size, dimensionality, backend and container resources; historical timings should not be treated as current service guarantees.

## References

- [Application discovery REST API](../applications.md)
- [Job submission API](../jobs.md)
- [Historical CAESAR-REST tutorial (examples; may use superseded option names)](https://github.com/SKA-INAF/caesar-rest)
