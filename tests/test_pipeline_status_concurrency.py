"""Regression tests for concurrent explicit pipeline synchronization."""

from copy import deepcopy
from types import SimpleNamespace

from caesar_rest.pipeline import manager
from caesar_rest.pipeline import status


class FakeRuns:
	def __init__(self):
		self.record = {
			'_id': 'mongo-id-1',
			'owner': 'alice',
			'pipeline_id': 'p1',
			'run_id': 'r1',
			'job_id': 'j1',
			'status': 'SUBMITTED'
		}
		self.last_filter = None

	def find(self, query):
		# Return a snapshot that can become stale.
		if query.get('status') == 'COMPLETED':
			return []

		return [deepcopy(self.record)]

	def update_one(self, query, update):
		self.last_filter = query

		# Simulate another monitor advancing the run
		# after synchronize_pipeline() read its snapshot.
		if self.record['status'] == 'SUBMITTED':
			self.record['status'] = 'RUNNING'
			self.record['synchronized_at'] = 'newer-observation'

		if self.record['status'] not in query['status']['$in']:
			return SimpleNamespace(modified_count=0)

		self.record.update(update['$set'])
		return SimpleNamespace(modified_count=1)


class FakeJobs:
	def find_one(self, query):
		return {
			'job_id': 'j1',
			'pipeline_id': 'p1',
			'run_id': 'r1',
			'state': 'RUNNING'
		}


class FakeMongo:
	def __getitem__(self, name):
		assert name == 'alice.jobs'
		return FakeJobs()


def test_stale_running_observation_does_not_overwrite(
		monkeypatch):

	runs = FakeRuns()

	monkeypatch.setattr(
		manager,
		'get_pipeline',
		lambda owner, pipeline_id: {}
	)

	monkeypatch.setattr(
		manager,
		'collections',
		lambda: (None, runs, None)
	)

	monkeypatch.setattr(
		status.mongo,
		'db',
		FakeMongo()
	)

	result = status.synchronize_pipeline('alice', 'p1')

	assert result['updated'] == []
	assert result['unchanged'] == 1

	assert runs.record['status'] == 'RUNNING'
	assert runs.record['synchronized_at'] == 'newer-observation'

	assert runs.last_filter['status'] == {
		'$in': ['SUBMITTED']
	}
