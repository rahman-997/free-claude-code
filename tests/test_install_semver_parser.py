"""Checks the actual portable Shell version parser without sourcing the installer."""
import subprocess
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"


def test_version_parser_preserves_shell_ifs_and_rejects_untrusted_fields():
    source = INSTALLER.read_text(encoding="utf-8")
    prefix = "stable_version_is_supported() {"
    end = "\nverify_uv() {"
    assert source.count(prefix) == 1
    function = source.split(prefix, 1)[1].split(end, 1)[0]
    function = prefix + function
    script = function + """
set -eu
IFS=:
stable_version_is_supported 0.11.16 0.11.16 || exit 10
[ "$IFS" = ":" ] || exit 11
stable_version_is_supported 0.12.0 0.11.16 || exit 12
[ "$IFS" = ":" ] || exit 13
if stable_version_is_supported 0.11.15 0.11.16; then exit 14; fi
if stable_version_is_supported 0.11.16-rc.1 0.11.16; then exit 15; fi
if stable_version_is_supported '0.11.16;echo unsafe' 0.11.16; then exit 16; fi
if stable_version_is_supported 0.11 0.11.16; then exit 17; fi
if stable_version_is_supported 0.11.16.4 0.11.16; then exit 18; fi
[ "$IFS" = ":" ] || exit 19
"""
    result = subprocess.run(["sh", "-c", script], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
