"""Namespace tool alias regression tests with no external API calls."""

import hashlib

from free_claude_code.core.openai_responses.tools import (
    responses_tool_identity_from_anthropic_name,
    responses_tool_name_to_anthropic_name,
)


def test_long_namespaced_alias_uses_sha256_and_remains_bounded():
    namespace = "team_" + "n" * 40
    name = "function_" + "x" * 60
    combined = namespace + "__" + name
    alias = responses_tool_name_to_anthropic_name(name, namespace=namespace)
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
    assert len(alias) == 64
    assert alias.endswith("_" + digest)
    assert alias == responses_tool_name_to_anthropic_name(name, namespace=namespace)


def test_long_namespaced_alias_round_trips_to_original_identity():
    namespace = "team_" + "n" * 40
    name = "function_" + "x" * 60
    tools = [
        {
            "type": "namespace",
            "name": namespace,
            "tools": [{"type": "function", "name": name}],
        }
    ]
    alias = responses_tool_name_to_anthropic_name(name, namespace=namespace)
    identity = responses_tool_identity_from_anthropic_name(tools, alias)
    assert (identity.kind, identity.name, identity.namespace) == (
        "function",
        name,
        namespace,
    )


def test_short_namespaced_tool_name_remains_unchanged():
    assert responses_tool_name_to_anthropic_name("read", namespace="fs") == "fs__read"
    assert responses_tool_name_to_anthropic_name("read") == "read"
