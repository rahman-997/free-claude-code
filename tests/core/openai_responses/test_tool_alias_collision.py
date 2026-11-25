"""Reject ambiguous aliases without changing distinct tool identities."""

import pytest

from free_claude_code.core.openai_responses.errors import ResponsesConversionError
from free_claude_code.core.openai_responses.tools import convert_tools


def function(name):
    return {"type": "function", "name": name}


def namespace(name, *tools):
    return {"type": "namespace", "name": name, "tools": list(tools)}


@pytest.mark.parametrize(
    "tools",
    [
        [function("fs__read"), namespace("fs", function("read"))],
        [namespace("a.b", function("read")), namespace("a_b", function("read"))],
        [namespace("fs", function("read"), {"type": "custom", "name": "read"})],
        [function("read"), function("read")],
    ],
)
def test_duplicate_alias_is_rejected(tools):
    with pytest.raises(
        ResponsesConversionError, match="Duplicate converted Responses tool name"
    ):
        convert_tools(tools)


def test_distinct_aliases_keep_order_and_names():
    result = convert_tools(
        [function("read"), namespace("fs", function("read")), {"type": "web_search"}]
    )
    assert result is not None
    assert [tool["name"] for tool in result] == ["read", "fs__read"]


def test_empty_and_absent_tools_preserve_contract():
    assert convert_tools(None) is None
    assert convert_tools([]) == []
