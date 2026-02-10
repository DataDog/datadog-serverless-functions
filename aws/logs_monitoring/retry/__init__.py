from retry.base_storage import BaseStorage
from settings import DD_SQS_QUEUE_URL


def create_storage(function_prefix) -> BaseStorage:
    """Select the appropriate storage backend based on configuration.

    If DD_SQS_QUEUE_URL is set, use SQS. Otherwise, fall back to S3.
    The S3 backend may be initialized with an empty bucket name when the
    retry feature is disabled (DD_STORE_FAILED_EVENTS=false) — this is
    safe because storage methods are only called when retry is enabled.
    """
    if DD_SQS_QUEUE_URL:
        from retry.sqs_storage import SQSStorage

        return SQSStorage(function_prefix)
    else:
        from retry.storage import S3Storage

        return S3Storage(function_prefix)
