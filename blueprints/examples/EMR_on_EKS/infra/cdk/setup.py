
import setuptools


setuptools.setup(
    name="emr_eks_cdk",
    version="0.0.1",

    description="EMR on EKS app",
    long_description="EMR on EKS ",
    long_description_content_type="text/markdown",

    author="author",

    package_dir={"": "stacks"},
    packages=setuptools.find_packages(where="stacks"),

    install_requires=[
        "aws-cdk.core==2.31.2",
        "aws-cdk.aws-emrcontainers==2.31.2",
        "aws-cdk.aws-eks==2.31.2",
        "aws-cdk.aws-ec2==2.31.2",
        "aws-cdk.aws-emr==2.31.2",
        "aws-cdk.aws_acmpca==2.31.2",
        "aws-cdk.aws-s3-deployment==2.31.2",
        "pyOpenSSL",
        "boto3",
        "awscli"
    ],

    python_requires=">=3.6",

    classifiers=[
        "Development Status :: 4 - Beta",

        "Intended Audience :: Developers",

        "License :: OSI Approved :: Apache Software License",

        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",

        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",

        "Typing :: Typed",
    ],
)
