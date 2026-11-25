# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Local development image for the agent (AgentCore Runtime uses the zip from scripts/build-agent.sh).
# Build context: the airflow-ui-agent directory. Run scripts/vendor-skills.sh build/agent/skills first.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY agent/requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY agent/main.py ./
COPY agent/mwaa_agent ./mwaa_agent
COPY build/agent/skills ./skills

USER 1000:1000
EXPOSE 8080
CMD ["python", "main.py"]
