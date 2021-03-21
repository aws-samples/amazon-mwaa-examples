#!/bin/sh

# exit script on error
set -e

if ! command -v aws &> /dev/null
then
	echo "aws cli not installed"
    exit 1
fi

echo "Number of arguments: $#"
echo "args: $@"
for key in "$@"
do
case $key in
    --envname=*)
    NAME="${key#*=}"
    echo "NAME = $NAME"
    shift
    ;;

    --dag=*)
    DAG="${key#*=}"
    echo "DAG = $DAG"
    shift
    ;;

    --command=*)
    COMMAND="{\"command\":\"${key#*=}\"}"
    echo "COMMAND = $COMMAND"
    shift
    ;;

    *)
    echo "unknown option"
    ;;

esac
done

CLI_JSON=$(aws mwaa create-cli-token --name $NAME) \
  && CLI_TOKEN=$(echo $CLI_JSON | jq -r '.CliToken') \
  && WEB_SERVER_HOSTNAME=$(echo $CLI_JSON | jq -r '.WebServerHostname') \
  && CLI_RESULTS=$(curl -s --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli" \
  --header "Authorization: Bearer $CLI_TOKEN" \
  --header "Content-Type: text/plain" \
  --data-raw "trigger_dag $DAG --conf '$COMMAND'") \
  && echo "Output:" \
  && echo $CLI_RESULTS | jq -r '.stdout' | base64 --decode \
  && echo "Errors:" \
  && echo $CLI_RESULTS | jq -r '.stderr' | base64 --decode

aws logs tail "airflow-$NAME-Task" --since 1m --follow --format short