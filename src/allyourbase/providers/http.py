"""Bounded HTTP retries with redacted diagnostics and per-attempt accounting."""

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from allyourbase.models.settings import AccessSettings
from allyourbase.providers.contracts import ProviderError


@dataclass(frozen=True)
class RequestObservation:
    provider: str
    operation: str
    status_code: int | None
    elapsed_seconds: float
    processing_units: float | None
    decoded_response_bytes: int | None = None


class Transport:
    def __init__(
        self,
        client: httpx.Client,
        settings: AccessSettings,
        attempts: int,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.settings = settings
        self.attempts = attempts
        self.sleep = sleep
        self.observations: list[RequestObservation] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        provider: str,
        operation: str,
        json_body: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        retry: bool = True,
        max_bytes: int | None = None,
    ) -> httpx.Response:
        attempts = self.attempts if retry else 1
        for attempt in range(attempts):
            start = time.monotonic()
            try:
                with self.client.stream(
                    method,
                    url,
                    json=json_body,
                    data=form,
                    headers=headers,
                    timeout=self.settings.http_timeout_seconds,
                    follow_redirects=False,
                ) as streamed:
                    chunks = []
                    size = 0
                    for chunk in streamed.iter_bytes():
                        size += len(chunk)
                        if max_bytes is not None and size > max_bytes:
                            raise ProviderError("response_size_limit", provider)
                        chunks.append(chunk)
                    decoded_headers = dict(streamed.headers)
                    decoded_headers.pop("content-encoding", None)
                    decoded_headers.pop("content-length", None)
                    response = httpx.Response(
                        streamed.status_code,
                        headers=decoded_headers,
                        content=b"".join(chunks),
                        request=streamed.request,
                    )
            except ProviderError:
                self.observations.append(
                    RequestObservation(
                        provider,
                        operation,
                        streamed.status_code,
                        time.monotonic() - start,
                        self._units(streamed),
                    )
                )
                raise
            except httpx.RequestError:
                self.observations.append(
                    RequestObservation(
                        provider,
                        operation,
                        None,
                        time.monotonic() - start,
                        None,
                    )
                )
                if attempt + 1 == attempts:
                    raise ProviderError("network_error", provider) from None
                self.sleep(self._delay(attempt, None))
                continue
            units = self._units(response)
            self.observations.append(
                RequestObservation(
                    provider,
                    operation,
                    response.status_code,
                    time.monotonic() - start,
                    units,
                    len(response.content),
                )
            )
            if response.status_code == 401:
                raise ProviderError("authentication_failed", provider)
            if response.status_code == 403:
                raise ProviderError("access_denied", provider)
            if (
                response.status_code == 429 or response.status_code >= 500
            ) and attempt + 1 < attempts:
                self.sleep(self._delay(attempt, response))
                continue
            if not 200 <= response.status_code < 300:
                raise ProviderError(f"http_{response.status_code}", provider)
            return response
        raise ProviderError("retry_limit", provider)

    def json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("max_bytes", self.settings.max_metadata_response_bytes)
        response = self.request(method, url, **kwargs)
        try:
            payload = response.json()
        except ValueError:
            raise ProviderError("invalid_json_response", str(kwargs["provider"])) from None
        if not isinstance(payload, dict):
            raise ProviderError("invalid_json_response", str(kwargs["provider"]))
        return payload

    def _units(self, response: httpx.Response) -> float | None:
        raw = response.headers.get(self.settings.processing_units_header)
        if raw is None:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if math.isfinite(value) and value >= 0 else None

    def _delay(self, attempt: int, response: httpx.Response | None) -> float:
        delay = self.settings.retry_base_seconds * 2**attempt
        if response is not None:
            try:
                if "retry-after" in response.headers:
                    delay = float(response.headers["retry-after"])
                elif "x-ratelimit-retry-after" in response.headers:
                    delay = float(response.headers["x-ratelimit-retry-after"]) / 1000
            except ValueError:
                pass
        if not math.isfinite(delay):
            delay = self.settings.max_retry_delay_seconds
        return float(max(0, min(delay, self.settings.max_retry_delay_seconds)))
