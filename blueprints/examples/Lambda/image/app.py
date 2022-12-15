import json

import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow import Table
import s3fs
import pandas as pd

s3 = s3fs.S3FileSystem()

def lambda_handler(event, context):
    fs = s3fs.S3FileSystem(
        anon=False,
        use_ssl=True,
    )

    print(event)
    s3_filepath = f's3://{event["bucket"]}/{event["key"]}'
    s3_bucket = event["bucket"]
    output_key = event["key"].replace(
        "tripdata.parquet", "processed").replace("input/", "")
    s3_output_filepath = f's3://{s3_bucket}/output/{output_key}'
    print(s3_output_filepath)

    pf = pq.ParquetDataset(
        s3_filepath,
        filesystem=fs)

    table = pf.read()
    df = table.to_pandas()

    if 'fhv_tripdata' in s3_filepath:
        print('Processing FHV Data')
        df.sort_values(by='dispatching_base_num', inplace=True)
        df = df['dispatching_base_num'].value_counts().rename_axis(
            'unique_values').to_frame('counts')
        df.reset_index(inplace=True)
        df = df.rename(columns={'index': 'disp num'})
        df = df[['unique_values', 'counts']]

        output_table = Table.from_pandas(df)
        #pq.write_to_dataset(Table.from_pandas(df_unique_sorted), s3_output_filepath, filesystem=s3, use_dictionary=True, compression='snappy')

    if 'green_tripdata' in s3_filepath:
        print('Processing Green Taxi Data')
        aggregate = table.group_by('trip_type').aggregate([
            ("fare_amount", 'sum')])
        sorted_aggregate = aggregate.sort_by([("trip_type", "ascending")])
        trip_type = sorted_aggregate.column(1)
        fare_amount_sum = sorted_aggregate.column(0)
        names = ["trip_type", "fare_amount_sum"]
        output_table = pa.table([trip_type, fare_amount_sum], names=names)
        #pq.write_to_dataset(reversed_table, s3_output_filepath, filesystem=s3, use_dictionary=True, compression='snappy')

    if 'yellow_tripdata' in s3_filepath:
        print('Processing Yellow Taxi Data')
        aggregate = table.group_by('payment_type').aggregate([
            ("fare_amount", 'sum')])
        sorted_aggregate = aggregate.sort_by([("payment_type", "ascending")])
        payment_type = sorted_aggregate.column(1)
        fare_amount_sum = sorted_aggregate.column(0)
        names = ["payment_type", "fare_amount_sum"]
        output_table = pa.table([payment_type, fare_amount_sum], names=names)

    print(output_table)
    pq.write_to_dataset(output_table, s3_output_filepath,
                        filesystem=s3, use_dictionary=True, compression='snappy')

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "success",
        }),
    }
