# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.
from setuptools import setup

setup(
    name="aws-dd-forwarder",
    version="0.0.0.dev0",
    description="Datadog AWS Forwarder Lambda Function",
    url="https://github.com/DataDog/datadog-serverless-functions/tree/master/aws/logs_monitoring",
    author="Datadog, Inc.",
    author_email="dev@datadoghq.com",
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="datadog aws lambda layer",
    python_requires=">=3.10, <3.12",
    install_requires=[
        "datadog-lambda==5.87.0",
        "requests-futures==1.0.0",
        "requests==2.31.0",
        "ddtrace==2.6.5",
        "urllib3==1.26.18",
        "datadog==0.48.0",
        "wrapt==1.16.0",
        "opentelemetry-api==1.23.0",
        "xmltodict==0.13.0",
        "bytecode==0.15.1",
        "protobuf==4.25.3",
        "ddsketch==2.0.4",
        "cattrs==23.2.3",
        "typing-extensions==4.10.0",
        "envier==0.5.1",
        "six==1.16.0",
        "attrs==23.2.0",
        "deprecated==1.2.14",
        "importlib-metadata==6.11.0",
        "charset-normalizer==3.3.2",
        "idna==3.6",
        "certifi==2024.2.2",
        "exceptiongroup==1.1.1",
        "zipp==3.17.0",
    ],
    extras_require={
        "dev": ["nose2==0.9.1", "flake8==3.7.9", "requests==2.22.0", "boto3==1.10.33"]
    },
    py_modules=[],
)
