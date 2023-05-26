# Orchestrating jobs in EKS

## Description

The set of sample files in the folder creates an MWAA environment with permission to create/delete EKS cluster and run a job in EKS Pod.

## Setup

**_These steps setup CDK in the development or the build environment_**

1. Install AWS CDK following the steps at [this link](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html)

2. All cdk commands use AWS_PROFILE to get the credentials.
   use [this link](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html) to
   setup ```aws profile```
3. Change the name of the S3 bucket so that it is globally unique

      File: infra/cdk/app.py, 
      change dagss3location from mwaa-s3-bucket-placeholder-version to mwaa-s3-bucket-[your initials]-version

#### Install Infrastructure

These commands provision the infrastructure needed to run the workload

- Vpc with Subnets and Security Groups
- IAM roles and associated policies needed to run MWAA
- S3 Bucket to store the artifacts needed for MWAA
- An empty MWAA environment

1. Setup the infrastructure using the command

```shell
      pip install -r ./infra/cdk/requirements.txt
      make AWS_PROFILE=[your aws_profile]       
```    

2. If you are creating the EKS cluster using the MWAA DAG, it needs the role for the node group to be pre-created

```shell
      make AWS_PROFILE=[your aws_profile] cdk-setup-eks-role
```
3. Copy the output **_NODEGROUPROLEARN_**. This is the role_arn used for EKS and will be needed later
4. Deploy the example DAGS and the requirements.txt file into the S3 bucket

```shell
    make AWS_PROFILE=[your aws_profile] cdk-deploy-to-bucket
```

5. Update the configurations for the mwaa environment

**Many customers have existing existing MWAA environments. If you have an existing environment, you can skip the creation above. This change will need a restart to the MWAA environment**

![edit env](images/edit_environment.png)


Add the path to requirements.txt file in the mwaa environment

![requirements](images/requirements.png)

Add a variable cdk.nodegroup_role with the value of the NODEGROUPROLEARN created above 

![nodegroup_role](images/nodegroup_variable.png)

6. This completes the setup. The rest of the steps are performed in the MWAA environment

7. Run the create_eks_cluster_nodegroup DAG to create the EKS cluster

8. Run the eks_run_pod to execute a sample pod using EksPodOperator

9. Once done, Run delete_eks_cluster_nodegroup to delete the cluster

10. [BONUS]: To update or add a DAGs, add them to examples/EKS/cdk/dags and deploy

```shell
    make AWS_PROFILE=[your aws_profile] cdk-deploy-to-bucket
```

### AWS CDK based infrastructure

The following DAGs are included in the repo

- *create_eks_cluster_nodegroup:* creates the ```EKS cluster and nodegroup```

- *eks_run_pod:* runs a sample ```pod``` on the created ```EKS cluster```

- *delete_eks_cluster_nodegroup:* deletes the previously created ```node group and EKS Cluster```

