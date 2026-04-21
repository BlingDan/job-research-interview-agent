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


def test_init_uses_settings_defaults_when_explicit_args_missing(monkeypatch):
    from app.core import llm as llm_module

    client_kwargs: Dict[str, object] = {}

    class DummyOpenAI:
        def __init__(self, **kwargs: object):
            client_kwargs.update(kwargs)

    monkeypatch.setattr(
        llm_module,
        "get_settings",
        lambda: SimpleNamespace(
            llm_model_id="settings-model",
            llm_api_key="settings-key",
            llm_base_url="https://llm.example.com/v1",
            llm_timeout=45,
        ),
        raising=False,
    )
    monkeypatch.setattr(llm_module, "OpenAI", DummyOpenAI)

    llm = JobResearchLLM()

    assert llm.model == "settings-model"
    assert llm.api_key == "settings-key"
    assert llm.base_url == "https://llm.example.com/v1"
    assert llm.timeout == 45
    assert client_kwargs == {
        "api_key": "settings-key",
        "base_url": "https://llm.example.com/v1",
        "timeout": 45,
    }


def test_init_explicit_args_override_settings_defaults(monkeypatch):
    from app.core import llm as llm_module

    client_kwargs: Dict[str, object] = {}

    class DummyOpenAI:
        def __init__(self, **kwargs: object):
            client_kwargs.update(kwargs)

    monkeypatch.setattr(
        llm_module,
        "get_settings",
        lambda: SimpleNamespace(
            llm_model_id="settings-model",
            llm_api_key="settings-key",
            llm_base_url="https://llm.example.com/v1",
            llm_timeout=45,
        ),
        raising=False,
    )
    monkeypatch.setattr(llm_module, "OpenAI", DummyOpenAI)

    llm = JobResearchLLM(
        model="explicit-model",
        api_key="explicit-key",
        base_url="https://explicit.example.com/v1",
        timeout=10,
    )

    assert llm.model == "explicit-model"
    assert llm.api_key == "explicit-key"
    assert llm.base_url == "https://explicit.example.com/v1"
    assert llm.timeout == 10
    assert client_kwargs == {
        "api_key": "explicit-key",
        "base_url": "https://explicit.example.com/v1",
        "timeout": 10,
    }


def test_invoke_retries_on_rate_limit_then_returns_full_text(monkeypatch):
    from app.core import llm as llm_module

    llm = JobResearchLLM(
        api_key="test-key",
        base_url="http://localhost:11434",
        model="gpt-4o-mini",
    )

    sleep_calls: List[float] = []
    call_count = 0

    class FakeRateLimitError(Exception):
        def __init__(self):
            super().__init__("rate limited")
            self.status_code = 429

    def _create(**kwargs: object):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise FakeRateLimitError()
        return _create_non_stream_response("after retry")

    monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    llm.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    result = llm.invoke([{"role": "user", "content": "hello"}])

    assert result == "after retry"
    assert call_count == 2
    assert sleep_calls == [1.0]


def test_invoke_does_not_retry_non_rate_limit_errors(monkeypatch):
    from app.core import llm as llm_module

    llm = JobResearchLLM(
        api_key="test-key",
        base_url="http://localhost:11434",
        model="gpt-4o-mini",
    )

    sleep_calls: List[float] = []
    call_count = 0

    def _create(**kwargs: object):
        nonlocal call_count
        call_count += 1
        raise ValueError("boom")

    monkeypatch.setattr(llm_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    llm.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create))
    )

    with pytest.raises(RuntimeError, match="boom"):
        llm.invoke([{"role": "user", "content": "hello"}])

    assert call_count == 1
    assert sleep_calls == []


def test_invoke_is_non_stream_only():
    llm = JobResearchLLM(
        api_key="test-key",
        base_url="http://localhost:11434",
        model="gpt-4o-mini",
    )

    with pytest.raises(TypeError):
        llm.invoke([{"role": "user", "content": "hello"}], stream=True)
