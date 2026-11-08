"""MimirSynth's shared client library for agent integrations (docs/AGENT_CLIENT.md): the configuration contract, the calls to a brain,
secret redaction and the optional session capture.

The source of truth is `integrations/shared/python/mimirsynth_agent`. A plugin carries an exact copy of this folder, written by
`python integrations/shared/vendor.py`, because an agent installs a plugin's folder and nothing outside it; a test keeps the copies equal.
Standard library only, Python 3.8 or later.
"""
from __future__ import annotations

from . import capture, secretscan
from .client import MARKER, QUERY_MAX, ApiError, Client, fail_open, redact, request, url_for
from .config import CAPTURE_ALIASES, CAPTURE_MODES, DEFAULTS, KEYS, Config, config_path, default_path, load

CONTRACT_VERSION = 1   # bumped only when the configuration contract changes in a way an integration must follow

__all__ = ["CAPTURE_ALIASES", "CAPTURE_MODES", "CONTRACT_VERSION", "DEFAULTS", "KEYS", "MARKER", "QUERY_MAX", "ApiError", "Client",
           "Config", "capture", "config_path", "default_path", "fail_open", "load", "redact", "request", "secretscan", "url_for"]
