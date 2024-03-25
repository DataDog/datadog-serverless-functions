from steps.common import merge_dicts


class AwsAttributes:
    def __init__(self, log_group=None, log_stream=None, log_events=None, owner=None):
        self.log_group = log_group
        self.log_stream = log_stream
        self.log_events = log_events
        self.owner = owner
        self.lambda_arn = None

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

    def get_log_stream(self):
        return self.log_stream

    def get_log_events(self):
        return self.log_events

    def get_owner(self):
        return self.owner

    def set_lambda_arn(self, arn):
        self.lambda_arn = arn
