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

import sys
from awsglue.transforms import Join
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job

glueContext = GlueContext(SparkContext.getOrCreate())
args = getResolvedOptions(sys.argv, ["db_name", "target_bucket_name"])

# catalog: database and table names
db_name = args["db_name"] #"legislators"
tbl_persons = "persons_json"
tbl_memberships = "memberships_json"
tbl_organizations = "organizations_json"

# output s3 and temp directories
target_bucket = args["target_bucket_name"]
output_history_dir = "s3://" + target_bucket + "/output-dir/legislator_history"
output_lg_single_dir = "s3://" + target_bucket + "/output-dir/legislator_single"
output_lg_partitioned_dir = "s3://" + target_bucket + "/output-dir/legislator_part"
redshift_temp_dir = "s3://" + target_bucket + "/temp-dir/"

# Create dynamic frames from the source tables 
persons = glueContext.create_dynamic_frame.from_catalog(database=db_name, table_name=tbl_persons)
memberships = glueContext.create_dynamic_frame.from_catalog(database=db_name, table_name=tbl_memberships)
orgs = glueContext.create_dynamic_frame.from_catalog(database=db_name, table_name=tbl_organizations)

# Keep the fields we need and rename some.
orgs = orgs.drop_fields(['other_names', 'identifiers']).rename_field('id', 'org_id').rename_field('name', 'org_name')

# Join the frames to create history
l_history = Join.apply(orgs, Join.apply(persons, memberships, 'id', 'person_id'), 'org_id', 'organization_id').drop_fields(['person_id', 'org_id'])

# ---- Write out the history ----

# Write out the dynamic frame into parquet in "legislator_history" directory
print("Writing to /legislator_history ...")
glueContext.write_dynamic_frame.from_options(frame = l_history, connection_type = "s3", connection_options = {"path": output_history_dir}, format = "parquet")

# Write out a single file to directory "legislator_single"
s_history = l_history.toDF().repartition(1)
print("Writing to /legislator_single ...")
s_history.write.parquet(output_lg_single_dir)

# Convert to data frame, write to directory "legislator_part", partitioned by (separate) Senate and House.
print("Writing to /legislator_part, partitioned by Senate and House ...")
l_history.toDF().write.parquet(output_lg_partitioned_dir, partitionBy=['org_name'])

# Convert the data to flat tables
print("Converting to flat tables ...")
dfc = l_history.relationalize("hist_root", redshift_temp_dir)