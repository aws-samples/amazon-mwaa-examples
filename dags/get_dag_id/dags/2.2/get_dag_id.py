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

"""
Details
-------
get_dag_id.py

Description
-----------
based on https://medium.com/apache-airflow/magic-loop-in-airflow-reloaded-3e1bd8fb6671

This function, when referenced from an Airflow DAG, will return NULL if not part of a 
Celery Task execution, or will return the DAG ID string if it is.

Usage
-----
Use this to make your dag parsing smarter, i.e. skip DAG creation during tasks for all 
but the current DAG id, or skip retrieving data during the DAG scheduler parse that is
only needed during task execution.
"""

import setproctitle, ast

def GetCurrentDag():
    current_dag = None
    try:
        PROCTITLE_SCHEDULER_PREFIX = "airflow scheduler"
        PROCTITLE_SUPERVISOR_PREFIX = "airflow task supervisor: "
        PROCTITLE_TASK_RUNNER_PREFIX = "airflow task runner: "
        PROCTITLE_NEW_PYTHON_INTERPRETER = "/usr/bin/python3"
        proctitle = str(setproctitle.getproctitle())

        if not proctitle.startswith(PROCTITLE_SCHEDULER_PREFIX):       
            if proctitle.startswith(PROCTITLE_SUPERVISOR_PREFIX): # core.execute_tasks_new_python_interpreter = False
                args_string = proctitle[len(PROCTITLE_SUPERVISOR_PREFIX):]
                args = ast.literal_eval(args_string)
                if len(args) > 3 and args[1] == "tasks":
                    current_dag = args[3]
            elif proctitle.startswith(PROCTITLE_TASK_RUNNER_PREFIX): 
                args = proctitle[len(PROCTITLE_TASK_RUNNER_PREFIX):].split(" ")
                if len(args) > 0:         
                    current_dag = args[0]
            elif proctitle.startswith(PROCTITLE_NEW_PYTHON_INTERPRETER): # core.execute_tasks_new_python_interpreter = True
                args = proctitle[len(PROCTITLE_NEW_PYTHON_INTERPRETER):].split(" ")
                if len(args) > 0:         
                    current_dag = args[4]
    except Exception as e:
        print("DAG Parse Exception:",e)
    
    return current_dag

