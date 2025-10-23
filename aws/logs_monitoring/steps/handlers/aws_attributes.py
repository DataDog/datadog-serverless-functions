from steps.common import merge_dicts


class AwsAttributes:
    def __init__(
        self, context, log_group=None, log_stream=None, log_events=None, owner=None
    ):
        self.log_group = log_group
        self.log_stream = log_stream
        self.log_events = log_events
        self.owner = owner
        self.partition = self._get_aws_partition(context)
        self.lambda_arn = None
        self.account = None
        self.region = None

    def _get_aws_partition(self, context):
        if context.invoked_function_arn.startswith("arn:aws-cn:"):
            return "aws-cn"
        elif context.invoked_function_arn.startswith("arn:aws-us-gov:"):
            return "aws-us-gov"
        else:
            return "aws"

    def to_dict(self):
        awslogs = {
            "aws": {
                "awslogs": {
                    "logGroup": self.log_group,
                    "logStream": self.log_stream,
                    "owner": self.owner,
                }
            }
        }
        if arn := self.lambda_arn:
            return merge_dicts(awslogs, {"lambda": {"arn": arn}})

        return awslogs

    def get_log_group(self):
        return self.log_group

    def get_log_group_arn(self):
        return f"arn:{self.partition}:logs:{self.region}:{self.account}:log-group:{self.log_group}"

    def get_log_stream(self):
        return self.log_stream

    def get_log_events(self):
        return self.log_events

    def get_owner(self):
        return self.owner

    def set_lambda_arn(self, arn):
        self.lambda_arn = arn

    def set_account_region(self, arn):
        try:
            parts = arn.split(":")
            self.account = parts[4]
            self.region = parts[3]
        except Exception as e:
            raise Exception(f"Failed to parse account and region from ARN: {e}")
