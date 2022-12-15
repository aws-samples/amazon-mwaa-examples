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
    if len(sys.argv) != 3:
        print("""
        Usage: nyc_aggregations.py <s3_input_path> <s3_output_path> 
        """, file=sys.stderr)
        sys.exit(-1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    spark = SparkSession\
        .builder\
        .appName("NYC Aggregations")\
        .getOrCreate()

    sc = spark.sparkContext

    df = spark.read.parquet(input_path)
    df.printSchema
    df_out = df.groupBy('pulocationid', 'trip_type', 'payment_type').agg(sum('fare_amount').alias('total_fare_amount'))

    df_out.write.mode('overwrite').parquet(output_path)

    spark.stop()

