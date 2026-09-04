import pytest

from free_claude_code.cli.launchers import codex
from free_claude_code.config.settings import Settings


def test_codex_hoists_caller_config_before_fcc_route_overrides() -> None:
    command = codex.build_codex_launcher_command(
        binary_path="resolved-codex",
        argv=(
            "exec",
            "-c",
            "features.example=true",
            "--config=model_provider=caller-provider",
            "hello",
            "--",
            "-c",
            "literal-after-separator",
        ),
        settings=Settings(),
        proxy_root_url="http://127.0.0.1:9191",
    )

    exec_index = command.index("exec")
    caller_feature_index = command.index("features.example=true")
    caller_provider_index = command.index("model_provider=caller-provider")
    fcc_provider_index = command.index('model_provider="fcc"')
    assert caller_feature_index < exec_index
    assert caller_provider_index < fcc_provider_index < exec_index
    assert command[exec_index:] == [
        "exec",
        "hello",
        "--",
        "-c",
        "literal-after-separator",
    ]


@pytest.mark.parametrize(
    ("argument", "expected_option", "expected_value"),
    (("-c=foo=1", "-c", "foo=1"), ("--config=bar=2", "--config", "bar=2")),
)
def test_codex_normalizes_equals_config_overrides(
    argument: str, expected_option: str, expected_value: str
) -> None:
    config_args, remaining = codex.partition_codex_config_overrides(
        ("exec", argument, "hi")
    )
    assert config_args == [expected_option, expected_value]
    assert remaining == ["exec", "hi"]
