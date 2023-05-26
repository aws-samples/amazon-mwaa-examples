# mwaa-blueprints

## Description

This is a collection of getting started blueprints for building pipelines that run in Amazon Managed Workflows for Apache Airflow (MWAA). Below
is the high level structure and the key files

```sh
├── examples
│   ├── AWSGlue
│   │   ├── README.md
│   │   ├── dags
│   │   ├── infra
│   │   └── scripts
│   ├── EKS
│   │   ├── dags
│   │   ├── requirements.txt
│   │   └── infra
│   ├── EMR
│   │   ├── dags
│   │   └── spark
|   ├── ECS
│   │   ├── infra
│   │   ├── mwaa
|   |   └── README.md
|   |
│   ├── EMR_on_EKS
│   │   ├── infra
│   │   ├── dags
│   │   ├── spark
│   ├── Lambda
│   │   ├── dags
│   │   └── image
└── infra
    ├── cloudformation
    └── terraform
```

### Folder Structure Details

- **README.md:** This file with instructions on how to use the blueprints

- **Makefile:** A collection of make targets to run the various commands to setup infrastructure. To get detailed
  infromation about the make targets, run ```make help``` from the root folder

- **examples:** This folder has a collection of technology specific DAGs organized into specific subfolders. Review the
  subfolders for details

- **infra:** This folder has the infrastructure as code samples for creating example MWAA environment



## Installation

### CDK
This example creates MWAA environment along with permissions related to EKS. 
Setup Environment and execute examples [cdk](examples/EKS/README.md)
 
### Terraform

Access [terraform](../infra/terraform/README.md)

### AWS CloudFormation

Access [CloudFormation](../infra/cloudformation/README.md)

#### Examples

Access [Examples](examples/)

## Support

Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address,
etc.

## Roadmap

If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing

State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started.
Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps
explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce
the likelihood that the changes inadvertently break something. Having instructions for running tests is especially
helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment

Show your appreciation to those who have contributed to the project.

## License

For open source projects, say how it is licensed.

## Project status

If you have run out of energy or time for your project, put a note at the top of the README saying that development has
slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or
owner, allowing your project to keep going. You can also make an explicit request for maintainers.
