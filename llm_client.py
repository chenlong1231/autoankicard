from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import AppSettings
from prompts import SYSTEM_PROMPT, build_user_prompt
from schema import SchemaError, VocabularyCardData, parse_vocabulary_card


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    raw_text: str
    card: VocabularyCardData


class SiliconFlowClient:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def _request_json(self, payload: dict) -> dict:
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        request = Request(url, data=body, headers=headers, method="POST")

        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                data = response.read().decode("utf-8")
        except HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise LLMError(f"LLM request failed with HTTP {exc.code}: {error_text}") from exc
        except URLError as exc:
            raise LLMError(f"Could not reach SiliconFlow: {exc.reason}") from exc

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned non-JSON response: {exc}") from exc
        return parsed

    def generate_card(self, word: str) -> LLMResponse:
        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(word)},
            ],
            "temperature": 0.0,
            "max_tokens": max(256, int(self.settings.max_tokens)),
            "enable_thinking": bool(self.settings.enable_thinking),
        }
        parsed = self._request_json(payload)
        try:
            raw_text = parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM response did not include message content") from exc
        try:
            card = parse_vocabulary_card(raw_text)
        except SchemaError as exc:
            raise LLMError(str(exc)) from exc
        return LLMResponse(raw_text=raw_text, card=card)

    def generate_card_with_retry(self, word: str) -> LLMResponse:
        last_error: Optional[Exception] = None
        attempts = max(1, self.settings.retry_count + 1)
        for index in range(attempts):
            try:
                return self.generate_card(word)
            except Exception as exc:
                last_error = exc
                if index + 1 < attempts:
                    time.sleep(max(0.0, self.settings.retry_delay_seconds))
        if last_error is None:
            raise LLMError("Unknown LLM error")
        raise last_error
