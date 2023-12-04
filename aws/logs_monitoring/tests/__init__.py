from approvaltests.approvals import set_default_reporter
from approvaltests.reporters import GenericDiffReporter, GenericDiffReporterConfig


set_default_reporter(
    GenericDiffReporter(
        GenericDiffReporterConfig(
            "VSCODE",
            "/Applications/Visual Studio Code.app/contents/Resources/app/bin/code",
            ["-d"],
        )
    )
)
