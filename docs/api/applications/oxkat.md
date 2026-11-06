# OXKAT MeerKAT calibration pipeline (`oxkat`)

> This reference describes the application contract in the CAESAR-REST `devel` configurator. Actual applications and available options can be queried with `GET /caesar/api/v1.0/apps` and `GET /caesar/api/v1.0/app/{app_name}/describe`. Application registration does not guarantee that its execution container is installed on every deployment.

See [Application discovery API](../applications.md) and [Job submission API](../jobs.md).

## Purpose

Processes registered MeerKAT interferometric Measurement Sets through CAESAR-REST Scientific Pipeline V2. The implemented scientific stages are `GET_INFO`, `1GC`, `FLAG` and `2GC`; the configurator also declares unimplemented future `3GC_PEEL` and `3GC_FACET` stages. The application supports per-target planning, independent runs, retained artifacts and external experiment selection (for example by MAASAI).

## Inputs

**Supported scientific formats:** `ms` (registered Measurement Set datasets).

OXKAT uses a dataset-bound Pipeline V2 rather than a normal user-uploaded image/file job.

| Stage | Required scientific inputs |
| --- | --- |
| `GET_INFO` | Original registered Measurement Set |
| `1GC` | Original MS and retained `project_info` metadata from GET_INFO |
| `FLAG` | Retained calibrated target MS from 1GC plus compatible `project_info`; one target per run |
| `2GC` | Retained flagged target MS from FLAG plus compatible `project_info` and required stage-specific imaging products; one target per run |

Pipeline run registration freezes upstream artifact bindings. The input MS and retained upstream data remain immutable; processing uses private writable working copies.

## Outputs

Declared output families include:

| Stage / family | Representative artifact names |
| --- | --- |
| General | `manifest` (`oxkat_manifest.json`), `log` |
| GET_INFO | `project_info` (`project_info.json`) |
| 1GC | `preparation_script`, `working_measurement_sets`, `measurement_set_flagversions`, `gain_tables`, `gain_plots`, `visibility_plots`, `oxkat_config_overrides` |
| FLAG | `flag_execution_script`, `flag_images`, `flagged_target_measurement_sets` |
| 2GC | `gc2_execution_script`, `gc2_images`, `gc2_target_measurement_sets`, `gc2_gain_tables` |
| Imaging QA and previews | `image_qa`, `image_previews`, `sourcefind_logs`, `sourcefind_catalog_native`, `sourcefind_catalog_tables`, `sourcefind_catalog_regions` |

Scientific directories, especially Measurement Sets, are retained and accessed through pipeline artifact bindings. A lightweight diagnostic archive is not the same as the complete registered artifact inventory.

Output products are conditional on the scientific execution options and the actual job run. Consult job output or run-specific artifacts rather than assuming all declared products exist.

## Limitations

- `3GC_PEEL` and `3GC_FACET` are not yet implemented.
- FLAG and 2GC operate on one explicitly selected target per run.
- Downstream stages require retained upstream outputs; missing artifacts prevent readiness.
- Bulk planning / registration does not execute runs automatically.
- CAESAR-REST does not automatically evaluate image quality, select a best run or advance the scientific pipeline.
- An artifact being declared does not mean it exists for every run; inspect actual registered artifacts before downloading.

## Supported options

The following names are taken from the current configurator. Defaults and accepted values should be checked with the live `describe` endpoint before submission.

The generic application option dictionary exposes `stage` (default `GET_INFO`; available stage labels include the two reserved 3GC stages). In Pipeline V2, the stage is passed as a **top-level run-registration field**. Further stage-specific scientific parameters are validated by the pipeline option schema, including:

| Pipeline parameter | Meaning |
| --- | --- |
| `target` | Target identifier for FLAG and 2GC |
| `oxkat_config` | Validated OXKAT scientific configuration overrides |
| `preview_retention` | Preview-artifact retention profile for applicable stages |

Stage- and version-dependent `oxkat_config` keys must be obtained from the application schema/current Pipeline V2 reference, not guessed. The generic `job_options` dictionary alone is not a full specification of pipeline-specific scientific overrides.

## Example

Illustrative request to `POST /caesar/api/v1.0/job` (provide valid accessible input identifiers and a bearer token when authentication is enabled):

```json
{
  "app": "oxkat",
  "dataset_id": "<REGISTERED_MEERKAT_DATASET_ID>",
  "name": "MeerKAT calibration experiments"
}
```

## Further guidance

**This example is a Pipeline V2 creation payload, sent to** `POST /caesar/api/v1.0/pipelines`, **not** the legacy `/job` endpoint. For subsequent run registration, use the stage-specific schema and upstream artifact bindings documented in [Scientific Pipeline V2](../scientific-pipelines.md).

The pipeline explicitly separates registration, submission, evaluation, selection and advancement. A completed run may be downloaded by explicit run ID before any preferred run has been selected.
