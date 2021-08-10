# export environment variables from .env
include .env
export

VENV=infra/venv/bin
WITH_VENV=. $(VENV)/activate;

.PHONY: all
all:
	@echo "make venv                 - create a virtual environment"
	@echo "make synth                - test CDK stacks with .env variables"
	@echo "make deploy               - deploy the infrastructure"

.PHONY: venv
venv: venv/bin/activate

venv/bin/activate: requirements-dev.txt
	@echo "Installing dependencies"
	@test -d infra/venv || python3 -m venv infra/venv
	@$(VENV)/pip install --upgrade pip
	@$(VENV)/pip install -Ur requirements-dev.txt
	@touch $(VENV)/activate

.PHONY: synth
synth: venv
	@$(WITH_VENV) cdk synth "*"

.PHONY: deploy
deploy: venv
	@$(WITH_VENV) cdk bootstrap
	@$(WITH_VENV) cdk deploy --all

.PHONY: destroy
destroy: venv
	@$(WITH_VENV) cdk destroy --all
