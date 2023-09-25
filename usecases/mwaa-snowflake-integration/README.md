# Using Snowflake with Amazon MWAA for Orchestrating Data Pipelines

Customers rely on data from different sources such as mobile applications, clickstream events from websites, historical data and more to deduce meaningful patterns in order to optimize their products, services and processes. Using a data pipeline, which is a set of tasks used to automate the movement and transformation of data between different systems can reduce the time and effort needed to gain insights from the data. Apache Airflow and Snowflake have emerged as powerful technologies for data management and analysis.

Amazon Managed Workflows for Apache Airflow (Amazon MWAA) is a managed workflow orchestration service for Apache Airflow that makes it simple to set up and operate end-to-end data pipelines in the cloud at scale. Snowflake Data Cloud platform provides a single source of truth for all your data needs and allows organizations to store, analyze and share large amounts of data with ease. The Apache Airflow open-source community provides over 1,000 pre-built operators (plugins that simplify connections to services) for Apache Airflow to build data pipelines. 

Scripts in this Repo are based on [blog post](https://), where we provide an overview of orchestrating your data pipeline using Snowflake operators in your Amazon MWAA environment. We will define the steps needed to setup the integration between Amazon MWAA and Snowflake. The solution will provide an end-to-end automated workflow which includes data ingestion, transformation, analytics and consumption.

