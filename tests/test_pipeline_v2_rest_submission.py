"""REST submission adapter tests; no real MongoDB or Slurm traffic."""
from types import SimpleNamespace

import pytest
from flask import Flask

from caesar_rest.pipeline import manager
from caesar_rest.pipeline.submission import v2_rest_submission as v2


def payload(**changes):
    value = {
        'submission_version': 2,
        'app': 'oxkat',
        'pipeline_id': 'p1',
        'node_id': 'calibration',
        'run_id': 'r2',
        'job_options': {'stage': '1GC'},
    }
    value.update(changes)
    return value


class Runs:
    def __init__(self, run):
        self.run = run

    def find_one(self, query):
        if all(self.run.get(k) == v for k, v in query.items()):
            return dict(self.run)
        return None


class Jobs:
    def __init__(self):
        self.records = []
        self.fail = False

    def insert_one(self, doc):
        if self.fail:
            raise RuntimeError('database down')
        self.records.append(dict(doc))


class Database:
    def __init__(self, run):
        self.pipeline_runs = Runs(run)
        self.jobs = Jobs()

    def __getitem__(self, key):
        assert key == 'alice.jobs'
        return self.jobs


@pytest.fixture
def setup(monkeypatch):
    run = {
        'owner': 'alice', 'pipeline_id': 'p1',
        'node_id': 'calibration', 'run_id': 'r2',
        'status': 'PLANNED', 'application': 'oxkat',
        'parameters': {'stage': '1GC'}, 'dataset_id': None,
        'input_artifacts': [{'input_name': 'getinfo'}],
    }
    db = Database(run)
    app = Flask(__name__)
    app.config.update({
        'JOB_SCHEDULER': 'slurm',
        'PIPELINE_STAGED_EXECUTION_ENABLED': True,
        'PIPELINE_V2_APPLICATIONS': {
            'oxkat': {
                'parameters': {'stage': ['1GC']},
                'input_options': {'project-info': 'getinfo'},
            },
        },
        'PIPELINE_ARTIFACT_RETENTION_ROOT': '/retained/app',
        'PIPELINE_ARTIFACT_RETENTION_ROOT_CLUSTER': '/retained/cluster',
        'PIPELINE_PYTHON_EXECUTABLE': '/usr/bin/python3',
    })
    events = []
    monkeypatch.setattr(v2, 'mongo', SimpleNamespace(db=db))

    monkeypatch.setattr(v2, 'jobmgr_slurm', SimpleNamespace(
        app_jobdir='/jobs/app',
        cluster_jobdir='/jobs/cluster',
        app_datadir='/data/app',
        cluster_datadir='/data/cluster',
    ))
    
    monkeypatch.setattr(v2, 'utils', SimpleNamespace(get_uuid=lambda: 'testjob'))
    monkeypatch.setattr(manager, 'get_pipeline', lambda owner, pipeline_id: {
        'owner': owner, 'pipeline_id': pipeline_id
    })
    monkeypatch.setattr(manager, 'validate_identifier', lambda value, name: None)

    def prepare(*args, **kwargs):
        events.append(('prepare', args, kwargs))
        return {'assets': {
            'run_id': 'r2', 'workspace_app': '/jobs/app/alice/job_testjob',
        }}

    def submit(*args, **kwargs):
        events.append(('submit', args, kwargs))
        return {'scheduler_pid': 321, 'status': 'SUBMITTED'}

    monkeypatch.setattr(v2, 'claim_and_prepare_v2', prepare)
    monkeypatch.setattr(v2, 'submit_claimed_v2', submit)
    return app, db, events


def resolve_application(app, scheduler, options):
    assert (app, scheduler, options) == ('oxkat', 'slurm', {})
    return {'image': '/containers/oxkat.sif'}


def test_successful_submission_registers_job(setup):
    app, db, events = setup
    with app.app_context():
        result = v2.submit_v2('alice', payload(), resolve_application)
    assert result['job_id'] == 'testjob'
    assert result['pid'] == 321
    assert [event[0] for event in events] == ['prepare', 'submit']
    args = events[0][1]
    assert args[0:6] == (
        db, 'alice', 'p1', 'calibration', 'r2', 'testjob'
    )
    assert args[6:10] == (
        '/jobs/app/alice', '/jobs/cluster/alice',
        '/retained/app', '/retained/cluster'
    )
    assert args[10:13] == (
        '/containers/oxkat.sif', ['--stage=1GC'],
        {'project-info': 'getinfo'}
    )
    
    kwargs = events[0][2]

    assert kwargs['dataset_app_root'] == '/data/app'
    assert kwargs['dataset_cluster_root'] == '/data/cluster'
    assert kwargs['dataset_input_name'] == 'measurement_set'
    
    doc = db.jobs.records[0]
    assert doc['pipeline_id'] == 'p1'
    assert doc['run_id'] == 'r2'
    assert doc['output_root'] == '/jobs/app/alice/job_testjob/results'
    assert doc['output_layout'] == 'results_subdirectory_v2'


@pytest.mark.parametrize('changes', [
    {'run_id': 'another'},
    {'job_options': {'stage': '2GC'}},
    {'app': 'aegean'},
    {'submission_version': 1},
    {'data_inputs': {'format': 'abspath', 'data': '/tmp/x'}},
])
def test_invalid_request_does_not_prepare(setup, changes):
    app, db, events = setup
    with app.app_context():
        with pytest.raises(manager.PipelineError):
            v2.submit_v2('alice', payload(**changes), resolve_application)
    assert events == []
    assert db.jobs.records == []


def test_unconfigured_application_fails_closed(setup):
    app, db, events = setup
    app.config['PIPELINE_V2_APPLICATIONS'] = {}
    with app.app_context():
        with pytest.raises(manager.PipelineError, match='not enabled'):
            v2.submit_v2('alice', payload(), resolve_application)
    assert not events


def test_mixed_dataset_artifact_submission(setup):
    app, db, events = setup

    db.pipeline_runs.run['dataset_id'] = 'dataset1'

    policy = app.config['PIPELINE_V2_APPLICATIONS']['oxkat']
    policy['dataset_input_name'] = 'measurement_set'
    policy['input_options'] = {
        'project-info': 'getinfo',
        'input-ms': 'measurement_set'
    }

    with app.app_context():
        result = v2.submit_v2(
            'alice', payload(), resolve_application
        )

    assert result['job_id'] == 'testjob'
    assert [event[0] for event in events] == ['prepare', 'submit']

    prepare_args = events[0][1]
    prepare_kwargs = events[0][2]

    assert prepare_args[12] == {
        'project-info': 'getinfo',
        'input-ms': 'measurement_set'
    }

    assert prepare_kwargs['dataset_app_root'] == '/data/app'
    assert prepare_kwargs['dataset_cluster_root'] == '/data/cluster'
    assert prepare_kwargs['dataset_input_name'] == 'measurement_set'

def test_dataset_only_getinfo_submission(setup):
    app, db, events = setup

    db.pipeline_runs.run['dataset_id'] = 'dataset1'
    db.pipeline_runs.run['input_artifacts'] = []
    db.pipeline_runs.run['parameters'] = {'stage': 'GET_INFO'}

    app.config['PIPELINE_V2_APPLICATIONS']['oxkat'] = {
        'parameters': {
            'stage': ['GET_INFO']
        },
        'dataset_input_name': 'measurement_set',
        'input_options': {
            'input-ms': 'measurement_set'
        }
    }

    with app.app_context():
        result = v2.submit_v2(
            'alice',
            payload(job_options={'stage': 'GET_INFO'}),
            resolve_application
        )

    assert result['job_id'] == 'testjob'
    assert [event[0] for event in events] == ['prepare', 'submit']

    prepare_args = events[0][1]

    assert prepare_args[11] == ['--stage=GET_INFO']
    assert prepare_args[12] == {
        'input-ms': 'measurement_set'
    }

    assert len(db.jobs.records) == 1
    
def test_policy_rejects_unmapped_input(setup):
    app, db, events = setup
    app.config['PIPELINE_V2_APPLICATIONS']['oxkat']['input_options'] = {
        'project-info': 'other'
    }
    with app.app_context():
        with pytest.raises(manager.PipelineError, match='binding'):
            v2.submit_v2('alice', payload(), resolve_application)
    assert not events


def test_submission_failure_does_not_register_job(setup, monkeypatch):
    app, db, events = setup

    def failed_submit(*args, **kwargs):
        events.append(('submit_failed', args, kwargs))
        raise manager.PipelineError('Slurm outcome uncertain', 503)

    monkeypatch.setattr(v2, 'submit_claimed_v2', failed_submit)
    with app.app_context():
        with pytest.raises(manager.PipelineError, match='uncertain'):
            v2.submit_v2('alice', payload(), resolve_application)
    assert [event[0] for event in events] == ['prepare', 'submit_failed']
    assert db.jobs.records == []


def test_job_registration_failure_requires_reconciliation(setup):
    app, db, events = setup
    db.jobs.fail = True
    with app.app_context():
        with pytest.raises(manager.PipelineError, match='reconcile manually'):
            v2.submit_v2('alice', payload(), resolve_application)
    assert [event[0] for event in events] == ['prepare', 'submit']
