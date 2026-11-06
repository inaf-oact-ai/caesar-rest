# Similarity Search

## Overview

**Application name:** `similarity-search`

Similarity Search identifies similar astronomical images using nearest-neighbor retrieval on numerical feature vectors.

The application uses the [Faiss library](https://github.com/facebookresearch/faiss) to search for similar feature representations, using cosine similarity.

Two execution modes are supported:

1. **Dataset similarity search:** For each observation in an input feature dataset, retrieve its `k` nearest neighbors from the same dataset.
2. **Query-image similarity search:** Given an input template image, compute its feature representation using a pretrained model and retrieve the `k` most similar observations from an existing feature dataset.

The application is particularly useful for exploring large collections of astronomical images, identifying morphologically similar sources and supporting interactive similarity-based retrieval.

The application supports batch processing through CAESAR-REST.

**Tool categories:** `image`, `tabular`

## Input requirements

### Supported scientific formats

| Format | Description |
|---|---|
| `json` | Dataset containing observation metadata and numerical feature vectors |
| `ascii` | Tabular numerical feature data |
| `fits` | Astronomical image used as a query |
| `png` | Image used as a query |

Input files can be referenced using the supported CAESAR-REST data-reference mechanisms, such as registered dataset identifiers or uploaded file UUIDs.

These data-reference mechanisms are distinct from the scientific file formats.

### Feature dataset

The primary input is a dataset containing observations and their numerical feature vectors.

A typical JSON input has the following structure:

```json
{
  "data": [
    {
      "sname": "source_001",
      "filepaths": ["source_001.fits"],
      "id": 1,
      "label": "RADIO-GALAXY",
      "feats": [0.12, 0.56, 0.91, 0.33]
    },
    {
      "sname": "source_002",
      "filepaths": ["source_002.fits"],
      "id": 2,
      "label": "EXTENDED",
      "feats": [0.15, 0.51, 0.87, 0.39]
    }
  ]
}
```

The principal fields are:

| Field | Description |
|---|---|
| `sname` | Observation or source identifier |
| `filepaths` | Associated image file paths |
| `id` | Optional observation classification identifier |
| `label` | Optional observation classification label |
| `feats` | Numerical feature vector used for similarity calculations |

Additional metadata fields may be present in the input records.

Feature vectors should have consistent dimensions and represent comparable properties across observations.

### Dataset similarity search

This mode requires one input: a feature dataset.

The application finds the nearest neighbors of each observation within the supplied dataset.

The input is passed to the underlying scientific application using its `--inputfile` parameter.

### Query-image similarity search

This mode requires two inputs, in the following order:

1. A dataset containing previously computed feature vectors.
2. An input query image.

The query image is processed using the selected pretrained feature extractor.

Its representation is then compared with the feature vectors stored in the input dataset.

The underlying application receives the dataset through `--inputfile` and the query image through `--img`.

**Important:** The query embedding must be compatible with the feature representation of the indexed dataset. In particular, the feature-extraction model and preprocessing should be consistent.

## Supported options

The following options are defined in `SimilaritySearchAppConfigurator`.

### Input options

| Option | Type | Default | Description |
|---|---|---|---|
| `datalist-key` | string | `data` | JSON dictionary key containing the input observations |
| `selcols` | string | `""` | Comma-separated feature-column identifiers to select; empty selects all columns |

### Feature extraction options

| Option | Type | Default | Description |
|---|---|---|---|
| `model` | string (enum) | `simclr-smgps` | Pretrained feature extraction model used for query-image embeddings |

Currently, the only advertised model is:

- `simclr-smgps`: SimCLR feature extractor trained for radio astronomical images.

### Similarity search options

| Option | Type | Default | Description |
|---|---|---|---|
| `k` | integer | `10` | Number of nearest neighbors to retrieve |
| `score-thr` | float | `0.0` | Minimum similarity score threshold used to retain neighbors |
| `large-data-thr` | integer | `1000000` | Dataset size threshold above which approximate nearest-neighbor search is used |
| `nlist` | integer | `100` | Number of inverted lists in the Faiss IVFPQ index |
| `M` | integer | `8` | Number of product-quantization subquantizers |
| `nprobe` | integer | `10` | Number of inverted lists visited during approximate search |

The `k` option accepts values from 1 to 100000.

The `score-thr` option accepts values in the range `[0, 1]`.

The approximate-search parameters are relevant when the algorithm selects an approximate Faiss index.

Increasing `nprobe` generally improves retrieval recall at the expense of computational cost.

### Image preprocessing options

| Option | Type | Default | Description |
|---|---|---|---|
| `imgsize` | integer | `224` | Image resizing dimension in pixels |
| `zscale` | flag | `false` | Enable ZScale preprocessing |
| `zscale-contrast` | float | `0.25` | Contrast parameter used by ZScale |

The accepted range for `imgsize` is 8–1024 pixels.

The accepted range for `zscale-contrast` is `[0, 1]`.

Image preprocessing must be compatible with the preprocessing used to generate the feature vectors of the indexed dataset.

### Output and execution options

| Option | Type | Default | Description |
|---|---|---|---|
| `outfile` | string | `featdata_simsearch.json` | Filename of the JSON similarity-search results |
| `no-logredir` | flag | `false` | Disable redirection of execution logs to an output file |

The application is executed through the scientific script `run_simsearch.sh`.

CAESAR-REST automatically supplies the application's execution command and input-file arguments.

For the complete option metadata, including allowed values and validation ranges, query:

```http
GET /caesar/api/v1.0/app/similarity-search/describe
```

## Output products

### Similarity-search results

The expected primary scientific output is:

`featdata_simsearch.json`

The output filename can be customized using the `outfile` option.

The JSON result contains observations returned by the similarity-search procedure, together with their original metadata and similarity information.

A representative output structure is:

```json
{
  "data": [
    {
      "sname": "source_001",
      "filepaths": ["source_001.fits"],
      "id": 1,
      "label": "RADIO-GALAXY",
      "feats": [0.12, 0.56, 0.91, 0.33],
      "nn_index": 125,
      "nn_score": 0.96
    },
    {
      "sname": "source_002",
      "filepaths": ["source_002.fits"],
      "id": 2,
      "label": "EXTENDED",
      "feats": [0.15, 0.51, 0.87, 0.39],
      "nn_index": 856,
      "nn_score": 0.91
    }
  ]
}
```

The similarity-specific fields are:

| Field | Description |
|---|---|
| `nn_index` | Index of the matching observation in the original feature dataset |
| `nn_score` | Similarity score associated with the retrieved observation |

Most other fields preserve the original observation information from the feature dataset.

The number of returned neighbors is controlled by `k` and may be reduced by similarity-score filtering.

**Metadata status:** Although the configurator defines the `outfile` option, its `job_outputs` dictionary is currently empty. Consequently, the output above is documented from the application tutorial and option metadata, but is not yet advertised as a structured scientific product by the application-description endpoint.

## Examples

The examples use the CAESAR-REST legacy job submission API:

```http
POST /caesar/api/v1.0/job
```

Requests require an authenticated bearer token when authentication is enabled.

### Example 1: Query-image similarity search

Find the five images in the `smgps-feats-simclr` dataset most similar to a user-uploaded image.

The dataset contains feature representations of 178,057 image cutouts from the MeerKAT Galactic Plane Survey, with 512 features per observation.

The example assumes that the query image has already been uploaded to CAESAR-REST and assigned a file UUID.

Request payload:

```json
{
  "app": "similarity-search",
  "data_inputs": {
    "data": [
      "smgps-feats-simclr",
      "QUERY_IMAGE_UUID"
    ],
    "format": [
      "dataset",
      "uid"
    ]
  },
  "job_options": {
    "k": 5,
    "score-thr": 0.0,
    "model": "simclr-smgps",
    "imgsize": 224,
    "zscale": true,
    "zscale-contrast": 0.25,
    "outfile": "featdata_simsearch.json"
  }
}
```

The first input references the registered feature dataset.

The second input references the uploaded query image.

The query image is transformed into a feature vector using the `simclr-smgps` pretrained model.

Similarity Search then identifies the five most similar feature vectors in the dataset.

The requested output is written to `featdata_simsearch.json`.

### Example 2: Dataset nearest-neighbor search

Retrieve the ten nearest neighbors for each observation in the feature dataset.

Request payload:

```json
{
  "app": "similarity-search",
  "data_inputs": {
    "data": "smgps-feats-simclr",
    "format": "dataset"
  },
  "job_options": {
    "k": 10,
    "score-thr": 0.0,
    "outfile": "featdata_simsearch.json"
  }
}
```

In this mode, no separate query image is supplied.

The application performs nearest-neighbor retrieval using the feature vectors already stored in the dataset.

### Example 3: Selecting feature columns

The `selcols` option can be used to restrict the search to specific feature columns.

For example:

```json
{
  "app": "similarity-search",
  "data_inputs": {
    "data": "smgps-feats-simclr",
    "format": "dataset"
  },
  "job_options": {
    "k": 10,
    "selcols": "0,1,2,3,4",
    "score-thr": 0.0
  }
}
```

This configuration requests similarity search using the selected feature columns rather than the entire embedding vector.

## Job submission and retrieval

A job can be submitted using:

```bash
curl --fail-with-body \
  -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d @payload.json \
  "https://server.example.org:8444/caesar/api/v1.0/job"
```

The server returns a job identifier that can be used to monitor execution.

Retrieve job status with:

```http
GET /caesar/api/v1.0/job/{job_id}/status
```

Retrieve the job output archive with:

```http
GET /caesar/api/v1.0/job/{job_id}/output
```

For complete job management and authentication details, see the [Job submission and monitoring API](../jobs.md).

## Limitations

The following limitations are declared in the application configurator:

1. Similarity results depend on the numerical feature representation, preprocessing and training data of the selected model.
2. High numerical similarity does not necessarily imply identical astronomical properties or morphological classifications.
3. Query-image embeddings and indexed feature vectors must have compatible dimensions and representation semantics.
4. Approximate nearest-neighbor search can trade retrieval accuracy for computational performance.
5. Availability of pretrained feature extraction models depends on the installed scientific container.

Additional practical considerations include:

- Different feature-extraction models may produce substantially different similarity rankings.
- Similarity scores should be interpreted within the context of the chosen feature space.
- The `score-thr` option can exclude candidate neighbors whose similarity scores are below the requested threshold.
- Large datasets may require approximate indexing to reduce computational costs.
- Query-image preprocessing should match the preprocessing used when generating the dataset embeddings.

## References

- [Faiss — Similarity Search Library](https://github.com/facebookresearch/faiss)
- [CAESAR-REST application discovery API](../applications.md)
- [CAESAR-REST job submission API](../jobs.md)
- [CAESAR-REST repository](https://github.com/inaf-oact-ai/caesar-rest)

