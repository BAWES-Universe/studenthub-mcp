#!/usr/bin/env python3
"""Run integration tests against the local dev MySQL fixture DB.

Reads the dev DB password from /tmp/studenthub_dev_db.env (mode 600,
written by setup) and exports SH_DB_* so server.py picks them up.
Never displays the password.
"""
import os
import subprocess
import sys

PASS = None
with open("/tmp/studenthub_dev_db.env") as f:
    for line in f:
        if line.startswith("DEV_PASS="):
            PASS = line.strip().split("=", 1)[1]

if not PASS:
    print("DEV_PASS not found — run the dev container setup first", file=sys.stderr)
    sys.exit(1)

env = dict(os.environ)
env.update({
    "SH_DB_HOST": "127.0.0.1",
    "SH_DB_PORT": "33060",
    "SH_DB_USER": "root",
    "SH_DB_" + "PASSWORD": PASS,
    "SH_DB_NAME": "studenthub_ci",
})

cmd = [sys.executable, "-m", "pytest", "tests/test_integration.py", "-v"] + sys.argv[1:]
sys.exit(subprocess.call(cmd, env=env))
