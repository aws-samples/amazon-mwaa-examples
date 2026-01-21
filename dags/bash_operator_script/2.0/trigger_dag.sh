#!/bin/sh

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

if ! command -v aws &> /dev/null
then
	echo "aws cli not installed"
      exit 1
fi

if ! command -v jq &> /dev/null
then
	echo "jq is not installed"
      exit 1
fi

if ! command -v head &> /dev/null
then
	echo "head is not installed"
      exit 1
fi

if ! command -v awk &> /dev/null
then
	echo "awk is not installed"
      exit 1
fi

if ! command -v sleep &> /dev/null
then
	echo "sleep is not installed"
      exit 1
fi

REGION=$(aws configure get default.region)
if [ -z "$REGION" ]; then
      echo "no default region, using us-east-1"
      REGION='us-east-1'
fi

VERSION=$(aws --version 2>&1)
if [ "${VERSION:0:10}" != 'aws-cli/2.' ]; then
      echo "please update to awscli version 2"
      echo "https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
      exit 1
fi

# test if aws cli has mwaa, if not prompt for upgrade
aws mwaa list-environments --region $REGION > /dev/null 2>&1
RESULT=$?
if [ $RESULT -ne 0 ]; then
      echo "please update the aws cli, mwaa not found"
      exit 1
fi

echo "Number of arguments: $#"
echo "args: $@"
for key in "$@"
do
case $key in
    --envname=*)
    NAME="${key#*=}"
    if [ -z "$NAME" ];then
      echo "--envname is empty, requires a string value"
      exit 1
    fi
    echo "NAME = $NAME"
    shift
    ;;

    --dag=*)
    DAG="${key#*=}"
    if [ -z "$DAG" ];then
      echo "--dag is empty, requires a string value"
      exit 1
    fi
    echo "DAG = $DAG"
    shift
    ;;

    --command=*)
    COMMAND="${key#*=}"
    if [ -z "$COMMAND" ];then
          echo "--command is empty, requires a string value"
          exit 1
    fi
    COMMAND="{\"command\":\"${key#*=}\"}"
    echo "COMMAND = $COMMAND"
    shift
    ;;

    --region=*)
    REGION="${key#*=}"
    if [ -z "$REGION" ];then
          REGION=$(aws configure get default.region)
          echo "no region, using default region $REGION"
    fi
    shift
    ;;

    *)
    echo "unknown option"
    exit 1
    ;;

esac
done

# validate required params are there before running curl command
if [ -z "$NAME" ];then
      echo "--envname is required, please rerun with --envname=SOME_VALUE"
      exit 1
fi
if [ -z "$DAG" ];then
      echo "--dag is required, please rerun with --dag=SOME_VALUE"
      exit 1
fi
if [ -z "$COMMAND" ];then
      echo "--command is required, please rerun with --command=SOME_VALUE"
      exit 1
fi

echo "region = $REGION"
STD_OUTPUT=""
STD_ERROR=""
CLI_JSON=$(aws mwaa create-cli-token --name $NAME --region $REGION) \
  && CLI_TOKEN=$(echo $CLI_JSON | jq -r '.CliToken') \
  && WEB_SERVER_HOSTNAME=$(echo $CLI_JSON | jq -r '.WebServerHostname') \
  && CLI_RESULTS=$(curl -s --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli" \
  --header "Authorization: Bearer $CLI_TOKEN" \
  --header "Content-Type: text/plain" \
  --data-raw "dags trigger $DAG --conf '$COMMAND'") \
  && echo -n "Sent request to airflow using curl, Response body:" \
  && STD_OUTPUT=$(echo $CLI_RESULTS | jq -r '.stdout' | base64 --decode) \
  && echo $STD_OUTPUT \
  && echo -n "Errors:" \
  && STD_ERROR=$(echo $CLI_RESULTS | jq -r '.stderr' | base64 --decode) \
  && echo $STD_ERROR

RESULT=$?
if [ $RESULT -ne 0 ]; then
      exit 1
fi
# query for specific log stream to get exact logs
LOG_STREAM_PREFIX=$DAG/bash_command/$(echo $STD_OUTPUT | head -n 1 | awk -F"__|," '{gsub(":","_",$2); print $2}')

# query for dag status to make sure its finished and loop until if finishes
echo "waiting for run to finish..."
while [ true ]
do
      STD_OUTPUT="running"
      CLI_JSON=$(aws mwaa create-cli-token --name $NAME)
      CLI_TOKEN=$(echo $CLI_JSON | jq -r '.CliToken') \
      && WEB_SERVER_HOSTNAME=$(echo $CLI_JSON | jq -r '.WebServerHostname') \
      && CLI_RESULTS=$(curl -s "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli" \
      --header "Authorization: Bearer $CLI_TOKEN" \
      --header "Content-Type: application/json" \
      --data-raw "dags list-runs --state running -d $DAG ") \
      && echo -n "Dag status: " \
      && STD_OUTPUT=$(echo $CLI_RESULTS | jq -r '.stdout' | base64 --decode) \
      && echo $STD_OUTPUT | awk -F"DAG RUNS" '{print $2}' | awk -F"|" '{print $8}' \
      && echo -n "Errors:" \
      && STD_ERROR=$(echo $CLI_RESULTS | jq -r '.stderr' | base64 --decode) \
      && echo $STD_ERROR
      if [ -z "$(echo $STD_OUTPUT | grep "running")" ]; then
            echo "dag has finished running, printing logs:"
            break
      fi
      echo "waiting for 10 seconds..."
      sleep 10
done
# sleep for another 3 seconds just to give the logs a chance to get to the stream in time to query them
sleep 3
aws logs filter-log-events --log-group-name "airflow-$NAME-Task" --log-stream-name-prefix "$LOG_STREAM_PREFIX" --region $REGION --output text --query 'sort_by(events, &timestamp)[*].[message]'