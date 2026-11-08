"""The OpenClaw plugin against a test instance (#373): its hooks, tools and commands, registered on a stand-in for OpenClaw's plugin API,
run against a real server with a fresh brain and one token per role (the `agent_instance` fixture): recall injected, remember into
quarantine, a token that cannot said, fail open when the server is away, capture off by default and sent once with a contributor token.
The checks themselves are integrations/openclaw/test/live.test.ts; recall answers from the fixture's stand-in."""
import os
import re
import subprocess
from pathlib import Path

import pytest
from test_agent_contract import FALKOR, _node, agent_instance  # noqa: F401
from test_control import client  # noqa: F401

PLUGIN = Path(__file__).resolve().parents[2] / "integrations" / "openclaw"


@pytest.mark.skipif(not _node(), reason="the OpenClaw plugin needs Node 22.6 or later")
def test_the_openclaw_plugin_against_a_test_instance(agent_instance):  # noqa: F811
    env = {**os.environ, "MIMIRSYNTH_CONTRACT_URL": agent_instance.url, "MIMIRSYNTH_CONTRACT_BRAIN": agent_instance.brain,
           **{f"MIMIRSYNTH_CONTRACT_{k.upper()}": v for k, v in agent_instance.tokens.items()},
           "MIMIRSYNTH_CONTRACT_NEWS": "1" if FALKOR else ""}
    r = subprocess.run([_node(), "--experimental-strip-types", "--no-warnings", "--test", "test/live.test.ts"], cwd=PLUGIN, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert re.search(r"^# pass [1-9]", out, re.M) and re.search(r"^# fail 0", out, re.M), out
    assert re.search(rf"^# skipped {0 if FALKOR else 1}$", out, re.M), out   # only `news` needs a graph
    assert any("(openclaw)" in q for q in agent_instance.seen), "the plugin never recalled from the instance"
