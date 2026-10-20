from caesar_rest.pipeline.submission.identity_reconciliation import verified_job_evidence, attempt_comment


def test_scheduler_identity_needs_exact_unique_comment():
	run = {'submission_intent': {'attempt_id': 'a' * 32}, 'scheduler_pid': None}
	assert verified_job_evidence(run, [{'job_id': 42, 'comment': 'caesar-v2:' + 'a' * 32}])['scheduler_pid'] == 42
	assert verified_job_evidence(run, [{'job_id': 42, 'name': 'same-name'}]) is None
	assert verified_job_evidence(run, [{'job_id': 42, 'comment': 'caesar-v2:' + 'a' * 32},
		{'job_id': 43, 'comment': 'caesar-v2:' + 'a' * 32}]) is None
	assert verified_job_evidence(run, []) is None
