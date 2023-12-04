from approvaltests.approvals import *
from approvaltests.reporters import *


set_default_reporter(
    GenericDiffReporter(
        GenericDiffReporterConfig(
            "VSCODE",
            "/Applications/Visual Studio Code.app/contents/Resources/app/bin/code",
            ["-d"],
        )
    )
)
