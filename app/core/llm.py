import os
from typing import Iterator, List, Optional

from openai import OpenAI


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
        self.model = model or os.getenv("LLM_MODEL_ID", "gpt-3.5-turbo")
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.temperature = temperature
        self.max_tokens = max_tokens or 4096
        self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", "20"))

        if not self.model:
            raise ValueError("Model ID is required.")
        if not all([self.api_key, self.base_url]):
            raise ValueError("LLM_API_KEY and LLM_BASE_URL are required.")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

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
        try:
            return self.client.chat.completions.create(**request_kwargs)
        except TypeError as exc:
            # Some OpenAI-compatible gateways reject max_tokens for specific models.
            if "max_tokens" in str(exc) and "max_tokens" in request_kwargs:
                request_kwargs.pop("max_tokens", None)
                return self.client.chat.completions.create(**request_kwargs)
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
