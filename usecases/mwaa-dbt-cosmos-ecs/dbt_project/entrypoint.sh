#!/bin/sh
# entrypoint.sh - Fetch ECS task role credentials and run dbt
# DuckDB's credential_chain doesn't read ECS metadata, so we fetch creds explicitly
python3 -c "
import json, urllib.request, os
u = os.environ.get('AWS_CONTAINER_CREDENTIALS_RELATIVE_URI', '')
if u:
    r = json.loads(urllib.request.urlopen('http://169.254.170.2' + u).read())
    with open('/tmp/aws_env', 'w') as f:
        f.write('export AWS_ACCESS_KEY_ID=' + r['AccessKeyId'] + '\n')
        f.write('export AWS_SECRET_ACCESS_KEY=' + r['SecretAccessKey'] + '\n')
        f.write('export AWS_SESSION_TOKEN=' + r['Token'] + '\n')
        f.write('export AWS_DEFAULT_REGION=us-east-1\n')
"
if [ -f /tmp/aws_env ]; then
    . /tmp/aws_env
fi
exec "$@"
