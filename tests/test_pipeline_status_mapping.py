"""Regression tests for ordinary job to pipeline state mapping."""

import pytest

from caesar_rest.pipeline.status import desired_status


@pytest.mark.parametrize(
	'state,exit_code,expected',
	[
		('STARTED', None, 'RUNNING'),
		('RUNNING', None, 'RUNNING'),
		('SUCCESS', 0, 'COMPLETED'),
		('SUCCESS', '0', 'COMPLETED'),
		('SUCCESS', None, 'COMPLETED'),
		('SUCCESS', 1, 'FAILED'),
		('SUCCESS', '1', 'FAILED'),
		('FAILURE', 1, 'FAILED'),
		('ABORTED', None, 'FAILED'),
		('TIMED-OUT', None, 'FAILED'),
		('TIMEOUT', None, 'FAILED'),
		('CANCELLED', None, 'CANCELLED'),
		('CANCELED', None, 'CANCELLED'),
		('PENDING', None, None),
		('UNKNOWN', None, None),
	]
)
def test_job_state_mapping(state, exit_code, expected):
	assert desired_status({
		'state': state,
		'exit_code': exit_code
	}) == expected


def test_state_mapping_is_case_insensitive():
	assert desired_status({
		'state': 'success',
		'exit_code': 0
	}) == 'COMPLETED'
	
def test_cleared_slurm_job_has_unknown_outcome():
	assert desired_status({
		'state': 'CLEARED',
		'exit_code': -1
	}) is None
	
@pytest.mark.parametrize(
	'exit_code',
	[
		1,
		-1,
		'1',
		'-1'
	]
)
def test_nonzero_success_exit_code_is_failure(exit_code):
	assert desired_status({
		'state': 'SUCCESS',
		'exit_code': exit_code
	}) == 'FAILED'
