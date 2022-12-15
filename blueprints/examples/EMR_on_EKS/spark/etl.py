from pyspark.context import SparkContext
from pyspark.sql.session import SparkSession
from pyspark.sql.types import StructType, StructField, IntegerType,StringType
from pyspark.sql.functions import *
from pyspark import SparkContext
import sys

print (sys.argv)
s3srcpath = sys.argv[1]
s3datapath = sys.argv[2]

s3tgtpath = s3srcpath + "curatedzone"

def main():

        sc =SparkContext()
        sc.setLocalProperty("callSite.short", "AWS EMR on EKS Sample Job")
        spark = SparkSession(sc)
        schema = StructType([
        StructField("id", StringType(), True),
        StructField("year_date", StringType(), True),
        StructField("element", StringType(), True),
        StructField("data_value", StringType(), True),
        StructField("m_flag", StringType(), True),
        StructField("q_flag", StringType(), True),
        StructField("s_flag", StringType(), True),
        StructField("obs_time", StringType(), True)
        ])
        dfreadings = spark.read.csv(s3srcpath + f"{s3datapath}/weather_station_data.csv.gz", sep=',',schema =schema)



        dfstations = spark.read.csv(s3srcpath + f"{s3datapath}/station_lookup.txt")
        dfstationssplit = dfstations.select(
        dfstations._c0.substr(1,11).alias('id'),
        dfstations._c0.substr(1,2).alias('countrycode'),
        dfstations._c0.substr(14,9).alias('lat'),
        dfstations._c0.substr(22,9).alias('long'),
        dfstations._c0.substr(39,2).alias('state')
        )

        dfstationssplit.createOrReplaceTempView("stations_sparkvw")
        dfreadings.createOrReplaceTempView("readings_sparkvw")

        dfprocessed = spark.sql("select a.* ,b.countrycode , b.state from readings_sparkvw a, stations_sparkvw b where a.id = b.id and substring(year_date,1,4) ='2011' and element ='PRCP' and b.countrycode ='US'  ")


        dfprocessed.write.mode("overwrite").format('parquet').save(s3tgtpath)



if __name__ == "__main__":
    main()
