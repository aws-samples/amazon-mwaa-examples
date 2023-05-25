"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


from airflow import DAG, Dataset
from airflow.decorators import dag, task
import pendulum
from airflow.operators.bash import BashOperator


@dag(
    dag_id="python_version_checker",
    description="This dag demonstrates the use of BashOperator to find the Python version",
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    schedule=None,
    tags=["airflow2.4", "python-version"])
def python_version_checker():

    run_this = BashOperator(
        task_id="check_python_version",
        bash_command="python3 --version",
    )

    run_this


python_version_checker()
