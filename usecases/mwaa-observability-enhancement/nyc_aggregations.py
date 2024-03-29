'''
MIT No Attribution

Copyright <YEAR> <COPYRIGHT HOLDER>

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''
from __future__ import print_function
import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import sum

if __name__ == "__main__":
    #if len(sys.argv) != 3:
    ## -- NEW: accounting for the new arguments -- ##
    if len(sys.argv) != 6:
        print("""
        Usage: nyc_aggregations.py <s3_input_path> <s3_output_path> <dag_name> <task_id> <correlation_id>
        """, file=sys.stderr)
        sys.exit(-1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    dag_task_name = sys.argv[3] + "." + sys.argv[4]
    correlation_id = dag_task_name + " " + sys.argv[5]

    spark = SparkSession\
        .builder\
        .appName(correlation_id)\
        .getOrCreate()

    sc = spark.sparkContext
    
    ## Adding the correlation_id to the appName and logging based on correlation_id ##

    log4jLogger = sc._jvm.org.apache.log4j
    logger = log4jLogger.LogManager.getLogger(dag_task_name)
    logger.info("Spark session started: " + correlation_id)
   
    df = spark.read.parquet(input_path)
    df.printSchema
    df_out = df.groupBy('pulocationid', 'trip_type', 'payment_type').agg(sum('fare_amount').alias('total_fare_amount'))

    df_out.write.mode('overwrite').parquet(output_path)

    logger.info("Stopping Spark session: " + correlation_id)
    spark.stop()