from caching.cloudwatch_log_group_cache import CloudwatchLogGroupTagsCache
from caching.step_functions_cache import StepFunctionsTagsCache
from caching.s3_tags_cache import S3TagsCache
from caching.lambda_cache import LambdaTagsCache


class CacheLayer:
    def __init__(self, prefix):
        self._cloudwatch_log_group_cache = CloudwatchLogGroupTagsCache(prefix)
        self._s3_tags_cache = S3TagsCache(prefix)
        self._step_functions_cache = StepFunctionsTagsCache(prefix)
        self._lambda_cache = LambdaTagsCache(prefix)

    def get_cloudwatch_log_group_tags_cache(self):
        return self._cloudwatch_log_group_cache

    def get_s3_tags_cache(self):
        return self._s3_tags_cache

    def get_step_functions_tags_cache(self):
        return self._step_functions_cache

    def get_lambda_tags_cache(self):
        return self._lambda_cache
