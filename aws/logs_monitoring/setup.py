from setuptools import setup

setup(
    name="aws-dd-forwarder",
    version="0.0.0.dev0",
    description="Datadog AWS Forwarder Lambda Function",
    url="https://github.com/DataDog/datadog-serverless-functions/tree/master/aws/logs_monitoring",
    author="Datadog, Inc.",
    author_email="dev@datadoghq.com",
    classifiers=[
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    keywords="datadog aws lambda layer",
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, !=3.5.*, <4",
    install_requires=["datadog-lambda==2.16.0"],
    extras_require={
        "dev": ["nose2==0.9.1", "flake8==3.7.9", "requests==2.22.0", "boto3==1.10.33"]
    },
)
