## Prerequisites
- [Terraform CLI](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli)

## Get started

aws ecr get-login-password --region us-east-1 | docker
login --username AWS --password-stdin
711192592489.dkr.ecr.us-east-1.amazonaws.com

aws ecr create-repository --repository-name mwaa-local-
runner

docker image ls | grep amazon/mwaa-local | grep 2_2

docker tag 11aa22bb33cc 711192592489.dkr.ecr.us-east-
1.amazonaws.com/mwaa-local-runner

docker push 012345678910.dkr.ecr.us-east-
1.amazonaws.com/mwaa-local-runner