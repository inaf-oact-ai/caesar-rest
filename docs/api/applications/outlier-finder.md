# Outlier Finder

Outlier Finder detects anomalous observations in a feature table using scikit-learn IsolationForest and a configurable anomaly-score threshold.

**Registered app:** `outlier-finder`  
**Category:** `tabular`  
**Configurator:** [`caesar_rest/app_configurators/outlier_finder.py`](https://github.com/inaf-oact-ai/caesar-rest/blob/devel/caesar_rest/app_configurators/outlier_finder.py)

## Scientific purpose

Outlier Finder detects anomalous observations in a feature table using scikit-learn IsolationForest and a configurable anomaly-score threshold. Results can be used in subsequent exploratory workflows; they are not themselves an automatic scientific validation of labels or classes.

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

- **`outliers-json`** — JSON output (`outlier_data.json` by default) preserving input metadata and adding `is_outlier` and `outlier_score`.
- **`outliers-ascii`** — ASCII outlier results (`outlier_data.dat` by default).
- **`datascaler`** — Feature scaler, when produced.
- **`model`** — IsolationForest model, unless disabled.
- **`log`** — Execution log.

Output products are retrieved from the job output archive for ordinary jobs. For pipeline runs, consult the run-specific artifact inventory; a declared output is not proof of availability in an individual run.

## Supported options

The following options are declared in the `devel` application configurator. Defaults and types should be checked with the live `GET /app/outlier-finder/describe` response for the installed version.

| Option | Type | Default | Purpose |
| --- | --- | --- | --- |
| `datalist-key` | str | `data` | JSON data key |
| `selcols` | str | `empty` | Dash-separated feature-column indices |
| `nestimators` | int | `100` | Number of isolation trees |
| `max-features` | int | `-1` | Maximum features per tree; -1 for all |
| `max-samples` | float | `-1.0` | Sample fraction; -1 uses sklearn auto |
| `contamination` | float | `-1.0` | Expected anomaly fraction; nonpositive uses auto |
| `anomaly-thr` | float | `0.7` | Threshold above which an observation is considered anomalous |
| `normalize` | bool | `true` | Normalize features |
| `no-save-ascii` | bool | `false` | Disable ASCII |
| `no-save-json` | bool | `false` | Disable JSON |
| `no-save-model` | bool | `false` | Disable model |
| `no-save-features` | bool | `false` | Omit features from outputs |
| `outfile` | str | `outlier_data.dat` | ASCII output filename |
| `outfile-json` | str | `outlier_data.json` | JSON output filename |
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
  "app": "outlier-finder",
  "data_inputs": {
    "data": "smgps-feats-simclr",
    "format": "dataset"
  },
  "job_options": {
    "nestimators": 100,
    "max-samples": 0.2,
    "max-features": -1,
    "contamination": -1.0,
    "anomaly-thr": 0.7,
    "normalize": true,
    "no-save-ascii": true,
    "no-save-model": true
  }
}
```

The server returns a `job_id` that can be used for status monitoring and output retrieval. See [Jobs API](../jobs.md) for those endpoints. The request is a legacy single-job example, not a Pipeline V2 run-registration request.

## Limitations and interpretation

- Outlier scores and classifications depend on sampling, feature selection, contamination and anomaly threshold.
- Thresholds and hyperparameters should be calibrated against labelled examples when possible.

Execution time depends on dataset size, dimensionality, backend and container resources; historical timings should not be treated as current service guarantees.

## References

- [Application discovery REST API](../applications.md)
- [Job submission API](../jobs.md)
- [Historical CAESAR-REST tutorial (examples; may use superseded option names)](https://github.com/SKA-INAF/caesar-rest)
