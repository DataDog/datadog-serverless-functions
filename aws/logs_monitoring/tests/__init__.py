from approvaltests.approvals import set_default_reporter
from approvaltests.reporters import GenericDiffReporter, GenericDiffReporterConfig
from os import environ
from os.path import exists

# TODO: this can be removed when a new verison of approvaltests is released
# with this fix: https://github.com/approvals/ApprovalTests.Python/pull/150
if not environ.get("CI") and exists(
    "/Applications/Visual Studio Code.app/contents/Resources/app/bin/code"
):
    set_default_reporter(
        GenericDiffReporter(
            GenericDiffReporterConfig(
                "VSCODE",
                "/Applications/Visual Studio Code.app/contents/Resources/app/bin/code",
                ["-d"],
            )
        )
    )
