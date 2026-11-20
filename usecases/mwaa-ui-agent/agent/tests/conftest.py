# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import sys
from pathlib import Path

# Most tests exercise the operate tier; tests of the default (operations off) unset this.
os.environ.setdefault("ENABLE_AIRFLOW_OPERATIONS", "true")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
