from typing import Any, Dict, List
from types import SimpleNamespace

import pytest

from app.core.llm import JobResearchLLM


def _create_non_stream_response(text: str) -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _create_stream_response(chunks: List[str]) -> List[SimpleNamespace]:
    return [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=chunk))]
        )
        for chunk in chunks
    ]


def test_invoke_non_stream_returns_full_text():
    llm = JobResearchLLM(
        api_key="test-key",
        base_url="http://localhost:11434",
        model="gpt-4o-mini",
    )
    llm.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: _create_non_stream_response("full response")
            )
        )
    )

    result = llm.invoke([{"role": "user", "content": "hello"}])

    assert result == "full response"


def test_invoke_non_stream_retry_without_max_tokens_when_rejected():
    llm = JobResearchLLM(
        api_key="test-key",
        base_url="http://localhost:11434",
        model="gpt-4o-mini",
    )

    call_log: List[Dict[str, object]] = []

    def _create(**kwargs: object):
        call_log.append(kwargs)
        if "max_tokens" in kwargs:
            raise TypeError("got an unexpected keyword argument 'max_tokens'")
        return _create_non_stream_response("retried response")

    llm.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    result = llm.invoke([{"role": "user", "content": "hello"}])

    assert result == "retried response"
    assert len(call_log) == 2
    assert "max_tokens" in call_log[0]
    assert "max_tokens" not in call_log[1]


def test_invoke_is_non_stream_only():
    llm = JobResearchLLM(
        api_key="test-key",
        base_url="http://localhost:11434",
        model="gpt-4o-mini",
    )

    with pytest.raises(TypeError):
        llm.invoke([{"role": "user", "content": "hello"}], stream=True)
