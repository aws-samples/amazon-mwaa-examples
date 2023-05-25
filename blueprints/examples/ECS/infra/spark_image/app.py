"""
-*- coding: utf-8 -*-
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from pyspark.sql.functions import col, expr
from pyspark.sql import SparkSession
SPARK = SparkSession.builder.appName('MWAASparkBluePrint.com').getOrCreate()


DATA = [("2019-01-23", 1), ("2019-06-24", 2), ("2019-09-20", 3)]
# Create Spark data frame by incrementing it by 1
SPARK.createDataFrame(DATA).toDF("date", "increment") \
    .select(col("date"), col("increment"), \
      expr("add_months(to_date(date,'yyyy-MM-dd'), cast(increment as int))").alias("inc_date")) \
    .show()
