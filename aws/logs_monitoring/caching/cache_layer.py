from caching.cloudwatch_log_group_cache import CloudwatchLogGroupTagsCache
from caching.step_functions_cache import StepFunctionsTagsCache
from caching.s3_tags_cache import S3TagsCache
from caching.lambda_cache import LambdaTagsCache


class CacheLayer:
    def __init__(self):
        self.cloudwatch_log_group_cache = CloudwatchLogGroupTagsCache()
        self.s3_tags_cache = S3TagsCache()
        self.step_functions_cache = StepFunctionsTagsCache()
        self.lambda_cache = LambdaTagsCache()
        self.prefix = None

    def set_prefix(self, prefix):
        self.prefix = prefix
        self.cloudwatch_log_group_cache.set_cache_prefix(prefix)
        self.s3_tags_cache.set_cache_prefix(prefix)
        self.step_functions_cache.set_cache_prefix(prefix)
        self.lambda_cache.set_cache_prefix(prefix)

    def get_cloudwatch_log_group_tags_cache(self):
        return self.cloudwatch_log_group_cache

    def get_s3_tags_cache(self):
        return self.s3_tags_cache

    def get_step_functions_tags_cache(self):
        return self.step_functions_cache

    def get_lambda_tags_cache(self):
        return self.lambda_cache
