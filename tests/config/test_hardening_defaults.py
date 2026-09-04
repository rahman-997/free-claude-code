from free_claude_code.config.settings import Settings


def test_default_host_is_loopback() -> None:
    assert Settings().host == "127.0.0.1"


def test_explicit_wildcard_host_remains_supported() -> None:
    assert Settings.model_validate({"HOST": "0.0.0.0"}).host == "0.0.0.0"
