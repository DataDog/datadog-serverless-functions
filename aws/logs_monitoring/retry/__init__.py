from retry.base_storage import BaseStorage
from settings import DD_S3_BUCKET_NAME, DD_SQS_QUEUE_URL


def create_storage(function_prefix) -> BaseStorage:
    """Select the appropriate storage backend based on configuration.

    If DD_SQS_QUEUE_URL is set, use SQS. Otherwise, use S3 (requires DD_S3_BUCKET_NAME).
    """
    if DD_SQS_QUEUE_URL:
        from retry.sqs_storage import SQSStorage

        return SQSStorage(function_prefix)
    elif DD_S3_BUCKET_NAME:
        from retry.storage import S3Storage

        return S3Storage(function_prefix)
    else:
        raise ValueError(
            "No storage backend configured. Set DD_SQS_QUEUE_URL or DD_S3_BUCKET_NAME."
        )
