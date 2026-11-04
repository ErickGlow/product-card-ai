"""Клиент OpenAI-совместимого Chat Completions API (OpenRouter, OpenAI, локальные серверы)."""
import json
import time

import httpx

from .config import LLMSettings


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: LLMSettings, timeout: float = 90, retries: int = 3, log=None):
        self.s = settings
        self.timeout = timeout
        self.retries = retries
        self.log = log or (lambda msg: None)

    def _post(self, messages: list[dict]) -> tuple[int, str]:
        """POST с ОБЩИМ лимитом времени на весь ответ.

        Обычный read-timeout httpx сбрасывается на каждом полученном байте, а OpenRouter,
        пока модель думает, шлёт keep-alive пробелы — без общего лимита запрос может висеть бесконечно.
        """
        deadline = time.monotonic() + self.timeout
        chunks = []
        with httpx.stream(
            "POST", f"{self.s.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.s.api_key}"},
            json={"model": self.s.model, "messages": messages, "temperature": 0.3},
            timeout=httpx.Timeout(30, connect=15),
        ) as r:
            for chunk in r.iter_bytes():
                chunks.append(chunk)
                if time.monotonic() > deadline:
                    raise TimeoutError(f"модель не ответила за {self.timeout:.0f} с")
            return r.status_code, b"".join(chunks).decode("utf-8", errors="replace").strip()

    def complete(self, messages: list[dict]) -> str:
        last = "неизвестная ошибка"
        for attempt in range(self.retries):
            if attempt:
                self.log(f"повтор запроса через {2 ** attempt} с ({last})")
                time.sleep(2 ** attempt)  # 2, 4 сек
            self.log(f"запрос к {self.s.model}…")
            started = time.monotonic()
            try:
                status, body = self._post(messages)
            except httpx.TransportError as e:  # сетевые сбои
                last = f"сетевая ошибка: {e!r}"
                continue
            except TimeoutError as e:
                last = str(e)
                continue
            if status in (401, 403):
                raise LLMError("API отклонил ключ (401/403): проверьте LLM_API_KEY")
            if status == 429 or status >= 500:
                last = f"HTTP {status} — превышен лимит или сбой провайдера"
                continue
            if status >= 400:
                raise LLMError(f"HTTP {status}: {body[:300]}")
            try:
                data = json.loads(body)
                if "error" in data:  # OpenRouter может вернуть ошибку провайдера с кодом 200
                    last = f"ошибка провайдера: {str(data['error'])[:200]}"
                    continue
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                last = f"неожиданный формат ответа: {body[:200]}"
                continue
            if content and content.strip():
                self.log(f"ответ получен за {time.monotonic() - started:.0f} с")
                return content
            last = "пустой ответ модели"
        raise LLMError(f"LLM недоступна после {self.retries} попыток: {last}")
