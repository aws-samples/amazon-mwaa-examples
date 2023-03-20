
# Orchestrating ECS Workload using MWAA

## Description

The orchestration of Spark work load using Amazon MWAA is a very common use case for data analytics. Recently there are couple of addition in airflow operators, which easily helps in orchestrating ECS workload. This Project contains the blueprint for orchestrating spark workload on ECS cluster using Amazon MWAA.

## Getting Started

1. Set up your virtual environment.
2. Bootstrap the target account.
3. Clone Gitlab repo.
4. Deploy the solution.

# Set up Virtual environment

The project is set up using Python CDK. The `cdk.json` file tells the CDK Toolkit how to execute your app. AWS CDK, and Python needs to installed on the deployment server. Once Python and CDK are install virtualenv needs to be created.

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```


# Steps for cloning the repo

Install Gitlab client on MAC/Windows OS, and run below command to clone the repo by using SSH or HTTPS.

For SSH use below command.
```
$ git clone git@ssh.gitlab.aws.dev:mkpoddar/mwaaecsorchestrationblueprint.git
```

For HTTPS use below command.
```
$ git clone https://gitlab.aws.dev/mkpoddar/mwaaecsorchestrationblueprint.git
```

# Bootstrap target AWS account

The target account is bootstarped by running below command.
```
cdk bootstrap aws://{DEVOPS-ACCOUNT-NUMBER}/{REGION} --termination-protection
```

# Steps for deploying the solution

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdk synth
```

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

The solution can be deployed using command 

```
cdk deploy --all
```


## Validation
The solution is validated on below environment version
* airflow==2.4.3
* apache-airflow-providers-amazon==7.2.0


## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!
