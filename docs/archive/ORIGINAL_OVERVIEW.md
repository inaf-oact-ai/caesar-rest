<p align="left">
  <img src="share/CAESAR-REST_Architecture.png" alt="Software architecture"/ width="500" height="500">
</p>

# caesar-rest
caesar-rest is a REST-ful web service for astronomical source extraction and classification with the caesar source extractor [https://github.com/SKA-INAF/caesar]. The software is developed in python and consists of a few containerized microservices, deployable on standalone servers or on a distributed cloud infrastructure. The core component is the REST web application, based on the Flask framework and running behind a nginx+uwsgi http server, and providing APIs for managing the input data (e.g. data upload/download/removal) and source finding jobs (e.g. submit, get status, get outputs) with different job management systems (Kubernetes, Slurm, Celery). Additional services (AAI, user DB, log storage, job monitor, accounting) enable the user authentication, the storage and retrieval of user data and job information, the monitoring of submitted jobs, and the aggregation of service logs and user data/job stats.
Besides caesar, we also foresee to integrate other tools widely used in the radio community (e.g. Aegean, PyBDSF) and newly developed source finders based on deep learning models.    

### Scientific pipelines and agent orchestration

CAESAR-REST also provides an authenticated REST API for managing
multi-stage scientific pipelines on Slurm-based infrastructures.

The pipeline framework supports:

- Application-independent pipeline and experiment registration.
- Configurable scientific stages and execution parameters.
- Multiple alternative runs per logical pipeline node.
- Named input artifacts and immutable cross-stage dependencies.
- Registration and retention of file and directory artifacts.
- Selection of preferred completed runs, including concurrency-safe updates.
- Explicit scientific, artifact-readiness and submission-state reporting.
- One-shot job submission with safeguards against duplicate Slurm execution.

These capabilities support agent-driven scientific workflows, where
external orchestration systems such as MAASAI propose experiments,
evaluate results, select preferred runs and decide which stage to
execute next.

The API does not automatically select scientifically optimal runs
or execute downstream stages. These decisions remain under the
control of the orchestrating application.

See:

- [Pipeline V2 REST API](docs/pipeline_v2_api.md)
- [MAASAI integration guide](docs/maasai_integration.md)


## **Status**
This software is under development. Original implementation developed in python 2.7, switched to python 3.6 later on (some apps are only available for python 3), now testing on python 3.8/3.10.

## **Credit**
This software is distributed with GPLv3 license. If you use caesar-rest for your research, please add repository link or acknowledge authors in your papers.   

