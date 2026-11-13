# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Demo DAGs for trying the MWAA UI agent locally. Each one fails in a different, realistic way."""

from __future__ import annotations

import json
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

START = datetime(2026, 1, 1)


@dag(schedule=None, start_date=START, catchup=False, tags=["demo", "fails"])
def orders_etl():
    """Fails in the transform step: the source schema renamed a field."""

    @task
    def extract() -> list[dict]:
        return [
            {"order_id": 1, "customer": "a", "amount": 10.5},
            {"order_id": 2, "customer": "b", "total_amount": 99.0},  # upstream renamed the field
        ]

    @task
    def transform(rows: list[dict]) -> float:
        return sum(row["amount"] for row in rows)

    @task
    def load(total: float) -> None:
        print(json.dumps({"daily_total": total}))

    load(transform(extract()))


@dag(schedule=None, start_date=START, catchup=False, tags=["demo", "fails"])
def daily_report():
    """Fails in a shell step: the input file is not where the command expects it."""
    BashOperator(
        task_id="build_report",
        bash_command="set -euo pipefail; wc -l /usr/local/airflow/data/sales_$(date +%F).csv",
    )


@dag(schedule=None, start_date=START, catchup=False, tags=["demo"])
def healthy_pipeline():
    """Succeeds. Use it to try "Test this DAG end to end"."""

    @task
    def numbers() -> list[int]:
        return [1, 2, 3]

    @task
    def double(n: int) -> int:
        return n * 2

    double.expand(n=numbers())


orders_etl()
daily_report()
healthy_pipeline()
