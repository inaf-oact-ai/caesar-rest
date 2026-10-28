#!/usr/bin/env python
"""Setuptools compatibility shim; metadata and dependencies live in pyproject.toml."""
from setuptools import setup

setup(
	scripts=[
		"apps/run_app.py",
		"apps/run_jobmonitor.py",
		"apps/run_accounter.py",
		"apps/run_artifact_retention.py",
	],
	data_files=[
		("config", ["config/nginx/nginx.conf", "config/uwsgi/uwsgi.ini"]),
	],
)
