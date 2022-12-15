BASE := $(shell /bin/pwd)



build: ##=> Same as package except that we don't create a ZIP
	docker build -t taxi_analysis . 
	docker tag  taxi_analysis:latest $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com/taxi_analysis:latest

login:
	aws ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com    

deploy: ##=> Deploy app using previously saved SAM CLI configuration
	aws ecr create-repository --repository-name taxi_analysis --region $(REGION) --image-scanning-configuration scanOnPush=true --image-tag-mutability MUTABLE
	aws ecr set-repository-policy --repository-name taxi_analysis --policy-text file://ecrpolicy.json
	docker push $(ACCOUNT).dkr.ecr.$(REGION).amazonaws.com/taxi_analysis:latest
         
ci: ##=> Run full workflow - Install deps, build deps, and deploy
	$(MAKE) login
	$(MAKE) build
	$(MAKE) deploy
update:
	$(MAKE) login
	$(MAKE) build
	$(MAKE) deploy
cleanup:
	$(MAKE) login
	aws ecr delete-repository --repository-name taxi_analysis --region $(REGION)

