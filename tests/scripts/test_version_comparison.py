import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("sh") is None, reason="POSIX shell required")
@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("0.11.16", 0),
        ("0.12.0", 0),
        ("1.0.0", 0),
        ("0.11.15", 1),
        ("0.12.0-rc.1", 1),
        ("0.11.16+build.1", 0),
        ("1.2.3.4", 1),
        ("1..3", 1),
        ("1.2.x", 1),
    ],
)
def test_stable_version_comparison(current, expected):
    source = (Path(__file__).resolve().parents[2] / "scripts/install.sh").read_text()
    function = source.split("stable_version_is_supported() {", 1)[1].split("\n}", 1)[0]
    script = "stable_version_is_supported() {" + function + "\n}\n"
    script += 'stable_version_is_supported "$1" "0.11.16"\n'
    result = subprocess.run(["sh", "-c", script, "test", current], check=False)
    assert result.returncode == expected


def test_comparison_preserves_callers_version():
    source = (Path(__file__).resolve().parents[2] / "scripts/install.sh").read_text()
    function = source.split("stable_version_is_supported() {", 1)[1].split("\n}", 1)[0]
    script = "stable_version_is_supported() {" + function + "\n}\n"
    script += 'version=1.2.3; stable_version_is_supported "$version" "0.11.16"; [ "$version" = "1.2.3" ]\n'
    result = subprocess.run(["sh", "-c", script], check=False)
    assert result.returncode == 0
