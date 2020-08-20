import sys
import os

# hack to add this dir to the python path, which fixes an issue with
# generated python code having incorrect import paths
# see https://github.com/google/protobuf/issues/881
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
