"""
DAG Factory Loader
This file dynamically generates Airflow DAGs from YAML configuration files.
"""
from dagfactory import load_yaml_dags

# Load all YAML files with .yml or .yaml extension in the dags folder
load_yaml_dags(globals_dict=globals(), suffix=['.yml', '.yaml'])
