#!/bin/bash

# Compile .py files from .proto files
# You must run this after updating a .proto file

# Requires protoc, which can be installed with `brew install protobuf`

protoc *.proto --python_out=./