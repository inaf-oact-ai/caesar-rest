# CAESAR source finder (`caesar`)

> This reference describes the application contract in the CAESAR-REST `devel` configurator. Actual applications and available options can be queried with `GET /caesar/api/v1.0/apps` and `GET /caesar/api/v1.0/app/{app_name}/describe`. Application registration does not guarantee that its execution container is installed on every deployment.

See [Application discovery API](../applications.md) and [Job submission API](../jobs.md).

## Purpose

CAESAR detects compact and extended radio-continuum sources in FITS images. For compact sources it can identify components and estimate flux density, position, extent and morphology using two-dimensional Gaussian-mixture fitting. Source selection, local/global background estimation, nested-source searching, residual generation and parallel tiling are configurable.

## Inputs

**Supported scientific formats:** `fits`.

A single radio-continuum FITS image. The image should contain meaningful astronomical WCS and beam metadata for scientifically useful measurements.

## Outputs

The configurator advertises these families:

| Product | Declared artifact identifier / match | Notes |
| --- | --- | --- |
| Source catalogs | `catalog_json` (`catalog-*.json`), `catalog_ascii` | JSON output requires `save-catalog-to-json`; other formats depend on options |
| Fitted components | `catalog_components_json` (`catalog_fitcomp-*.json`), `catalog_components_ascii` | Present when fitted components are produced |
| ROOT results | `catalog_root` | Native CAESAR format |
| Region files | `region`, `region_components` | Source regions / fitted-component regions |
| Plots and images | `plot` | Diagnostic plots or visual products |
| Execution records | `script`, `config`, `log` | Reproducibility and diagnostics |

The configurator also exposes output-control flags for background, RMS, significance, saliency, segmented and residual maps.

Output products are conditional on the scientific execution options and the actual job run. Consult job output or run-specific artifacts rather than assuming all declared products exist.

## Limitations

- Detection quality depends on background estimation and source thresholds.
- Extended-source recovery depends on the chosen algorithm.
- Images larger than about 10,000 pixels can be computationally expensive; tiling and parallelism may help.
- Although the tool may process other wavelength regimes, the configurator notes that it has primarily been tested on radio images.

## Supported options

The following names are taken from the current configurator. Defaults and accepted values should be checked with the live `describe` endpoint before submission.

The configurator exposes a large scientific parameter surface. The groups below list the **exact option identifiers**; use `/app/caesar/describe` for individual types, bounds and defaults.

| Group | Notable parameters |
| --- | --- |
| Detection | `seedthr`, `mergethr`, `npixmin`, `compactsearchiters`, `seedthrstep`, `no-compactsearch`, `no-nestedsearch`, `no-extendedsearch` |
| Background | `globalbkg`, `bkgestimator`, `bkgbox`, `bkgboxpix`, `bkggrid`, `bkgskipoutliers`, `no-bkg2ndpass` |
| Source selection | `selectsources`, `circratiothr`, `elongationthr`, `maxnpix`, `nbeamsthr`, `no-circratiocut`, `no-elongationcut` |
| Nested sources | `blobmaskmethod`, `nested-blobthr`, `nested-blobminscale`, `nested-blobmaxscale`, `nested-blobscalestep` |
| Fitting | `fitsources`, `fit-maxcomponents`, `fit-maxnbeams`, `fit-minimizer`, `fit-minimizeralgo`, `fit-freebkg`, `fit-poslimit`, `fit-sigmalimit`, `fit-chi2cut` |
| Extended sources | `extsfinder`, `activecontour`, `saliency-thr`, `saliency-minreso`, `saliency-maxreso`, `ac-niters`, `cv-nitersinner` |
| Outputs | `save-catalog-to-json`, `save-fits`, `save-regions`, `save-summaryplot`, `save-bkgmap`, `save-rmsmap`, `save-residualmap` |
| Execution | `no-mpi`, `nproc`, `nthreads`, `tilesplit`, `tilesize`, `tilestep`, `mergeedgesources`, `no-logredir` |

Additional specialized fitting, residual-removal, filtering and extended-search controls are available from the live endpoint; the table is a navigation summary rather than a full replacement for the machine-readable option schema.

## Example

Illustrative request to `POST /caesar/api/v1.0/job` (provide valid accessible input identifiers and a bearer token when authentication is enabled):

```json
{
  "app": "caesar",
  "data_inputs": {"data": "<FITS_FILE_UID>", "format": "uid"},
  "job_options": {
    "save-catalog-to-json": true,
    "seedthr": 5.0,
    "mergethr": 2.5,
    "no-mpi": true,
    "no-nestedsearch": true,
    "no-extendedsearch": true
  }
}
```

## Further guidance

CAESAR is a source finder, not a learned image classifier. If a workflow needs source morphology labels, consider the separate classifier applications. Source-finder outputs and fitted-component outputs are not necessarily produced in every run.
