"""A stand-in for a headless CLI: reads the prompt on stdin and prints FAKE_CLI_OUTPUT.

FAKE_CLI_EXIT sets the exit code, FAKE_CLI_SLEEP makes it wait first. FAKE_CLI_ECHO prints the prompt instead."""

import os
import sys
import time

prompt = sys.stdin.read()
time.sleep(float(os.environ.get("FAKE_CLI_SLEEP", "0")))
if os.environ.get("FAKE_CLI_ECHO"):
    print(prompt)
else:
    print(os.environ.get("FAKE_CLI_OUTPUT", "{}"))
sys.exit(int(os.environ.get("FAKE_CLI_EXIT", "0")))
