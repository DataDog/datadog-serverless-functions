import os
import logging
from time import time
import datetime
import json
import boto3
from botocore.exceptions import ClientError
from settings import DD_RETRY_PATH, DD_S3_BUCKET_NAME

logger = logging.getLogger(__name__)
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


class Storage(object):
    def __init__(self, function_prefix):
        self.bucket_name = DD_S3_BUCKET_NAME
        self.s3_client = boto3.client("s3")
        self.function_prefix = function_prefix

    def get_data(self, prefix):
        keys = self._list_keys(prefix)
        key_data = {}
        for key in keys:
            key_data[key] = self._fetch_data_for_key(key)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Found {len(keys)} retry keys for prefix {prefix}")

        return key_data

    def store_data(self, prefix, data):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Storing retry data for prefix {prefix}")
        random_suffix = str(time())
        key_prefix = self._get_key_prefix(prefix)
        key = f"{key_prefix}{random_suffix}"
        serialized_data = self._serialize(data)
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name, Key=key, Body=serialized_data
            )
        except ClientError:
            logger.error(f"Failed to store retry data for prefix {prefix}")

    def delete_data(self, key):
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
        except ClientError:
            logger.error(f"Failed to delete retry data for key {key}")

    def get_lock(self, prefix, interval_seconds):
        key = self._get_lock_key(prefix)
        try:
            lock_file = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            last_modified_unix_time = self._get_last_modified_time(lock_file)
            if last_modified_unix_time + interval_seconds > time():
                return False
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchKey":
                logger.error(f"Failed to get retry lock for prefix {prefix}")

        try:
            # put lock file (create or update existing)
            self.s3_client.put_object(Bucket=self.bucket_name, Key=key)
        except ClientError:
            logger.error(f"Failed to put retry lock for prefix {prefix}")
            return False

        return True

    def _get_last_modified_time(self, s3_file):
        last_modified_str = s3_file["ResponseMetadata"]["HTTPHeaders"]["last-modified"]
        last_modified_date = datetime.datetime.strptime(
            last_modified_str, "%a, %d %b %Y %H:%M:%S %Z"
        )
        return int(last_modified_date.strftime("%s"))

    def _list_keys(self, prefix):
        key_prefix = self._get_key_prefix(prefix)
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=key_prefix
            )
            return [
                content["Key"]
                for content in response.get("Contents", [])
                if content["Key"] != self._get_lock_key(prefix)
            ]
        except ClientError as e:
            logger.error(
                f"Failed to list retry keys for prefix {key_prefix} because of {e}"
            )
            return []

    def _fetch_data_for_key(self, key):
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            body = response.get("Body")
            data = body.read()
            return self._deserialize(data)
        except ClientError:
            logger.error(f"Failed to fetch retry data for key {key}")
            return None
        except Exception as e:
            logger.error(
                f"Failed to deserialize retry data for key {key} because of {e}"
            )
            return None

    def _get_lock_key(self, prefix):
        return f"{self._get_key_prefix(prefix)}lock"

    def _get_key_prefix(self, retry_prefix):
        return f"{DD_RETRY_PATH}/{self.function_prefix}/{str(retry_prefix)}/"

    def _serialize(self, data):
        return bytes(json.dumps(data).encode("UTF-8"))

    def _deserialize(self, data):
        return json.loads(data.decode("UTF-8"))
