import pytest
from pydantic import ValidationError

from free_claude_code.core.anthropic.models import Message, MessagesRequest
from free_claude_code.core.openai_responses import OpenAIResponsesRequest


@pytest.mark.parametrize("value", (0, -1, -736))
def test_responses_rejects_nonpositive_max_output_tokens(value: int) -> None:
    with pytest.raises(ValidationError):
        OpenAIResponsesRequest(
            model="nvidia_nim/openai/gpt-oss-120b",
            input="hello",
            max_output_tokens=value,
        )


@pytest.mark.parametrize("value", (0, -1, -736))
def test_messages_rejects_nonpositive_max_tokens(value: int) -> None:
    with pytest.raises(ValidationError):
        MessagesRequest(
            model="claude-opus-5",
            max_tokens=value,
            messages=[Message(role="user", content="hello")],
        )


def test_output_token_limits_still_accept_positive_values_and_none() -> None:
    responses = OpenAIResponsesRequest(
        model="nvidia_nim/openai/gpt-oss-120b",
        input="hello",
        max_output_tokens=1,
    )
    messages = MessagesRequest(
        model="claude-opus-5",
        max_tokens=1,
        messages=[Message(role="user", content="hello")],
    )

    assert responses.max_output_tokens == 1
    assert messages.max_tokens == 1
    assert OpenAIResponsesRequest(model="m", input="hello").max_output_tokens is None
