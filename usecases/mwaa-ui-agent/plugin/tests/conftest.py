# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import sys
import tempfile
from pathlib import Path

# Keep Airflow from writing to ~/airflow during tests.
os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp(prefix="mwaa-agent-test-"))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
