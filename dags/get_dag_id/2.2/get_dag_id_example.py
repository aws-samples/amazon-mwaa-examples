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
get_dag_id_example.py

Description
-----------
example using get_dag_id for smart parsing

This creates N dags, one per table row, but will only retrieve SQL statement for 
particular table row if it is being called from a task

"""

import os
from datetime import datetime
from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator

DAG_ID = os.path.basename(__file__).replace(".py", "")
POSTGRES_CONN_ID='postgres_redshift'

# get current dag ID for smart parsing
from get_dag_id import GetCurrentDag
current_dag = GetCurrentDag()

# run a query
def run_query(sql):
    pg_request = sql
    pg_hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID,schema="dev")
    connection = pg_hook.get_conn()
    cursor = connection.cursor()
    cursor.execute(pg_request)
    results = cursor.fetchall()

    return results

# retrieve number of rows from a table
def get_num_rows():
    num_rows = -1
    try:
        pg_request = "select count(*) from user_query_list;"
        results = run_query(pg_request)
        num_rows=int(results[0][0])
    except Exception as e:
        print(e)
    return num_rows

# retrieve a specific row from the table
def get_query(row_num):
    sqlstring=""
    try:
        pg_request = f"""
            SELECT 
                sqlstring
            FROM
                (select 
                    taskid,
                    username,
                    sqlstring,
                    ROW_NUMBER () OVER (ORDER BY taskid) as row_number
                from user_query_list as u
                )
            WHERE
                row_number = {row_num}
            """
        results = run_query(pg_request)
        sqlstring=results[0][0]
    except Exception as e:
        print(e)
    return sqlstring

NUM_ROWS = get_num_rows()

for row_num in range(1,NUM_ROWS+1):
    dag_id=f"{DAG_ID}_{str(row_num).zfill(3)}"  

    #process all dags if not part of a task execution, otherwise just create one
    if current_dag == dag_id or not current_dag:
        @dag(
            dag_id=dag_id,
            schedule_interval=None,
            start_date=datetime(2022, 1, 1),
            catchup=False,
        )
        def update_table_dag():
            #if part of a task execution retrieve the SQL statement
            if(current_dag):
                sqlstring=get_query(row_num)        
            else:
                sqlstring=""            
            t = PostgresOperator(task_id="query_table",sql=sqlstring,postgres_conn_id=POSTGRES_CONN_ID)            
        globals()[dag_id] = update_table_dag()
