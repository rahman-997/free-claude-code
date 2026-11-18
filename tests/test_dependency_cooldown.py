"""Guard dependency cooldown settings against accidental removal.

Pure-stdlib checks: no package installation, API keys or network are required.
"""

import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_uv_resolver_delays_newly_published_packages():
    settings = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert settings["tool"]["uv"]["exclude-newer"] == "7 days"
    assert settings["tool"]["uv"]["required-version"] == ">=0.11.16"


def test_both_dependabot_ecosystems_have_cooldowns():
    config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    sections = re.split(r"(?m)^  - package-ecosystem:\s*", config)[1:]
    assert len(sections) == 2
    assert {section.splitlines()[0].strip().strip('"') for section in sections} == {
        "uv",
        "github-actions",
    }
    for section in sections:
        assert re.search(r"(?m)^    cooldown:\s*$\n      default-days: 7\s*$", section)
