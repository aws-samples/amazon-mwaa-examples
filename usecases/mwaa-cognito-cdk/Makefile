# Execute a sequence of actions
all: install build linting security unittest cooling

# Pipeline sequence
## The warming step pre-warms the evironment with:
install:
	@echo "Install modules local"
	npm i
installci:
	@echo "Install modules CI/CD pipeline"
	npm i

## This step builds applications and creates deliverable items
build:
	npm run cdk synth
buildci:
	export NODE_OPTIONS=--max_old_space_size=8192
	npm run cdk synth
## This step checks the code base with linting tools
linting:
	@echo "Check and fix liting locally"
	npm run format
lintingci:
	@echo "Liniting code check in CI/CD pipeline"
	npm run eslint
## This step executes unit tests for the code base
unittest:
	@echo "Unit test local execution"
	npm run test
unittestci:
	@echo "Unit test in CI/CD pipeline"
	npm run test
security:
	@echo "Check security locally"
	cfn_nag_scan -i ./cdk.out -t .\*.template.json

# Manual execution
## Cleanup the whole environment. Remove all temporary files
clean:
	git clean -xdf
## Deploy application to the Dev AWS account manually
deploy:
	npm run cdk -- deploy dev-* --require-approval never
