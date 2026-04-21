import time
from typing import Iterator, List, Optional

from openai import OpenAI

from app.core.config import get_settings


_MAX_RATE_LIMIT_RETRIES = 2
_INITIAL_RATE_LIMIT_BACKOFF_SECONDS = 1.0


class JobResearchLLM:
    """Small wrapper around an OpenAI-compatible chat client."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        **kwargs,
    ):
        settings = get_settings()

        self.model = model or settings.llm_model_id
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or settings.llm_base_url
        self.temperature = temperature
        self.max_tokens = max_tokens or 4096
        self.timeout = timeout or settings.llm_timeout

        if not self.model:
            raise ValueError("Model ID is required.")
        if not all([self.api_key, self.base_url]):
            raise ValueError("LLM_API_KEY and LLM_BASE_URL are required.")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        if getattr(exc, "status_code", None) == 429:
            return True

        response = getattr(exc, "response", None)
        return getattr(response, "status_code", None) == 429

    def _get_rate_limit_backoff_seconds(self, exc: Exception, retry_index: int) -> float:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) or {}
        retry_after = headers.get("retry-after")

        if retry_after is not None:
            try:
                retry_after_seconds = float(retry_after)
                if retry_after_seconds >= 0:
                    return retry_after_seconds
            except (TypeError, ValueError):
                pass

        return _INITIAL_RATE_LIMIT_BACKOFF_SECONDS * (2**retry_index)

    def _build_request_kwargs(
        self,
        messages: List[dict[str, str]],
        stream: bool,
    ) -> dict[str, object]:
        request_kwargs: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": stream,
        }
        if self.max_tokens:
            request_kwargs["max_tokens"] = self.max_tokens
        return request_kwargs

    def _call_completion(self, messages: List[dict[str, str]], stream: bool):
        request_kwargs = self._build_request_kwargs(messages=messages, stream=stream)
        rate_limit_retries = 0

        while True:
            try:
                return self.client.chat.completions.create(**request_kwargs)
            except TypeError as exc:
                # Some OpenAI-compatible gateways reject max_tokens for specific models.
                if "max_tokens" in str(exc) and "max_tokens" in request_kwargs:
                    request_kwargs.pop("max_tokens", None)
                    continue
                raise
            except Exception as exc:
                if self._is_rate_limit_error(exc) and rate_limit_retries < _MAX_RATE_LIMIT_RETRIES:
                    backoff_seconds = self._get_rate_limit_backoff_seconds(exc, rate_limit_retries)
                    time.sleep(backoff_seconds)
                    rate_limit_retries += 1
                    continue
                raise

    def invoke(self, messages: List[dict[str, str]]) -> str:
        """Run a non-streaming completion call and return the full text."""
        try:
            response = self._call_completion(messages=messages, stream=False)
            if response is None:
                raise RuntimeError("Empty response from LLM API.")

            choices = getattr(response, "choices", None)
            if not choices:
                return ""

            first_choice = choices[0]
            message = getattr(first_choice, "message", None)
            return getattr(message, "content", "") or ""
        except Exception as exc:
            raise RuntimeError(f"LLM API call failed: {exc}") from exc

    def think(self, messages: List[dict[str, str]]) -> Iterator[str]:
        """Run a streaming completion call and yield incremental text chunks."""
        try:
            response = self._call_completion(messages=messages, stream=True)
            if response is None:
                raise RuntimeError("Empty response from LLM API.")

            for chunk in response:
                if not getattr(chunk, "choices", None):
                    continue

                first_choice = chunk.choices[0]
                delta = getattr(first_choice, "delta", None)
                content = getattr(delta, "content", "") or ""
                if content:
                    yield content
        except Exception as exc:
            raise RuntimeError(f"LLM API call failed: {exc}") from exc
