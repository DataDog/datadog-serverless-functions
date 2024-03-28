from enum import Enum


class RetryPrefix(Enum):
    LOGS = "logs"
    METRICS = "metrics"
    TRACES = "traces"

    def __str__(self):
        return self.value
