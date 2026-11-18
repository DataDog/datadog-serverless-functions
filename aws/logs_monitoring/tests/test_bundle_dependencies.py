import hashlib
import io
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

FORWARDER_DIR = Path(__file__).resolve().parents[1]


class TestBundleDependencies(unittest.TestCase):
    """Exercise the release Dockerfile's pip command against an offline index."""

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.index = self.root / "index"
        self.index.mkdir()
        self.build = self.root / "build"
        self.build.mkdir()
        dockerfile = (FORWARDER_DIR / "tools/Dockerfile_bundle").read_text()
        commands = [
            shlex.split(line.removeprefix("RUN "))
            for line in dockerfile.replace("\\\n", " ").splitlines()
            if line.startswith("RUN pip install ")
        ]
        self.assertEqual(len(commands), 1)
        self.install_command = [sys.executable, "-m", "pip", "--isolated"] + commands[
            0
        ][1:]

    def wheel(self, name, version="1.0.0", requires=(), value="trusted"):
        path = self.index / f"{name}-{version}-py3-none-any.whl"
        dist_info = f"{name}-{version}.dist-info"
        files = {
            f"{name}.py": f"VALUE = {value!r}\n",
            f"{dist_info}/METADATA": (
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
                + "".join(f"Requires-Dist: {requirement}\n" for requirement in requires)
            ),
            f"{dist_info}/WHEEL": (
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
            ),
        }
        files[f"{dist_info}/RECORD"] = "".join(
            f"{name},,\n" for name in [*files, f"{dist_info}/RECORD"]
        )
        with zipfile.ZipFile(path, "w") as archive:
            for filename, content in files.items():
                archive.writestr(filename, content)
        return path

    def requirement(self, name, artifact):
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        return f"{name}==1.0.0 --hash=sha256:{digest}\n"

    def install(self, requirements):
        (self.build / "requirements.txt").write_text(requirements)
        return subprocess.run(
            self.install_command
            + [
                "--no-index",
                "--find-links",
                str(self.index),
                "--disable-pip-version-check",
            ],
            cwd=self.build,
            env={**os.environ, "PIP_CONFIG_FILE": os.devnull},
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_installs_locked_dependencies_even_when_newer_releases_exist(self):
        parent = self.wheel("forwarder_fixture", requires=("forwarder_child>=1",))
        child = self.wheel("forwarder_child")
        self.wheel("forwarder_fixture", version="9999.0.0", value="unreviewed")
        self.wheel("forwarder_child", version="9999.0.0", value="unreviewed")
        result = self.install(
            self.requirement("forwarder_fixture", parent)
            + self.requirement("forwarder_child", child)
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Check the installed modules can actually be imported from the bundle.
        imported = subprocess.run(
            [
                sys.executable,
                "-S",
                "-c",
                "import forwarder_fixture, forwarder_child; "
                "assert forwarder_fixture.VALUE == forwarder_child.VALUE == 'trusted'",
            ],
            cwd=self.build,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(imported.returncode, 0, imported.stderr)

    def test_rejects_replaced_wheel_at_locked_version(self):
        parent = self.wheel("forwarder_fixture", requires=("forwarder_child>=1",))
        child = self.wheel("forwarder_child")
        requirements = self.requirement("forwarder_fixture", parent) + self.requirement(
            "forwarder_child", child
        )
        self.wheel("forwarder_child", value="tampered")
        result = self.install(requirements)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("DO NOT MATCH THE HASHES", result.stderr)
        self.assertFalse((self.build / "forwarder_child.py").exists())

    def test_rejects_unlocked_transitive_dependency(self):
        parent = self.wheel("forwarder_fixture", requires=("forwarder_child>=1",))
        self.wheel("forwarder_child")
        result = self.install(self.requirement("forwarder_fixture", parent))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("must have their versions pinned", result.stderr)
        self.assertFalse((self.build / "forwarder_child.py").exists())

    def test_rejects_requirements_without_hashes(self):
        self.wheel("forwarder_fixture")
        result = self.install("forwarder_fixture==1.0.0\n")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Hashes are required", result.stderr)
        self.assertFalse((self.build / "forwarder_fixture.py").exists())

    def test_rejects_source_distribution_without_executing_build_code(self):
        marker = self.root / "setup-executed"
        source = self.index / "forwarder_fixture-1.0.0.tar.gz"
        setup = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n".encode()
        with tarfile.open(source, "w:gz") as archive:
            info = tarfile.TarInfo("forwarder_fixture-1.0.0/setup.py")
            info.size = len(setup)
            archive.addfile(info, io.BytesIO(setup))
        result = self.install(self.requirement("forwarder_fixture", source))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(marker.exists())
        self.assertIn(
            "No matching distribution found for forwarder_fixture==1.0.0", result.stderr
        )
        self.assertNotIn("Installing build dependencies", result.stdout + result.stderr)

    def test_every_locked_dependency_has_an_exact_version_and_sha256(self):
        lock = (FORWARDER_DIR / "requirements.txt").read_text().replace("\\\n", " ")
        requirements = [
            line.strip()
            for line in lock.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(requirements)
        for requirement in requirements:
            with self.subTest(requirement=requirement.split()[0]):
                self.assertRegex(requirement, r"^[\w.-]+==[\w.]+\s")
                hashes = re.findall(r"--hash=sha256:([0-9a-f]+)", requirement)
                self.assertTrue(hashes)
                self.assertTrue(all(len(digest) == 64 for digest in hashes))


if __name__ == "__main__":
    unittest.main()
