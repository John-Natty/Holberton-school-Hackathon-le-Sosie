"""Serve Flask locally in Docker and on a host that supplies PORT."""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 1
threads = 4
timeout = 60
# Do not log questions, CSV contents, or API credentials.
accesslog = None
errorlog = "-"
