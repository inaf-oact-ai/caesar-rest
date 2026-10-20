"""Read-only raw Slurm REST v0.0.36 lookup for exact attempt comments.

Do not confuse a missing job with a rejected submission: active /jobs
may omit completed jobs. Returns None on transport/parsing ambiguity.
"""
import requests


def raw_slurm_jobs(slurm_manager):
	"""Fetch raw records retaining 'comment' (simplified client drops it)."""
	try:
		if not slurm_manager.is_token_active():
			if slurm_manager.generate_token() < 0:
				return None
		url = slurm_manager.cluster_url.rstrip('/') + '/jobs'
		headers = {'Content-Type': 'application/json',
			'X-SLURM-USER-NAME': slurm_manager.username,
			'X-SLURM-USER-TOKEN': slurm_manager.token}
		reply = requests.get(url, headers=headers, timeout=slurm_manager.request_timeout)
		if reply.status_code != 200:
			return None
		payload = reply.json()
		if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
			return None
		return payload['jobs']
	except (requests.RequestException, ValueError, TypeError, AttributeError):
		return None
