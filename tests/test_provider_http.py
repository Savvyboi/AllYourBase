import gzip

import httpx
import pytest

from allyourbase.models.settings import Settings
from allyourbase.providers.auth import Credentials, TokenProvider
from allyourbase.providers.contracts import Asset, ProviderError
from allyourbase.providers.http import Transport


def test_retries_are_counted_and_bounded(settings: Settings) -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "999999"})
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        transport = Transport(client, settings.access, 3, sleep=delays.append)
        assert transport.json(
            "POST", "https://provider.invalid/search", provider="test", operation="search"
        ) == {"ok": True}
    assert calls == 2
    assert delays == [settings.access.max_retry_delay_seconds]
    assert [o.status_code for o in transport.observations] == [429, 200]


def test_network_error_does_not_leak_request(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-token-in-exception", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        transport = Transport(client, settings.access, 3, sleep=lambda _: None)
        with pytest.raises(ProviderError, match="network_error") as error:
            transport.request(
                "GET",
                "https://provider.invalid/?token=private-token",
                provider="test",
                operation="search",
            )
    assert "private-token" not in str(error.value)
    assert len(transport.observations) == 3


def test_process_request_is_not_retried_blindly(settings: Settings) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        transport = Transport(client, settings.access, 3, sleep=lambda _: None)
        with pytest.raises(ProviderError, match="http_503"):
            transport.request(
                "POST",
                "https://provider.invalid/process",
                provider="test",
                operation="radar_process",
                retry=False,
            )
    assert len(transport.observations) == 1


@pytest.mark.parametrize(
    "header,expected",
    [(None, None), ("0", 0), ("1.25", 1.25), ("nan", None), ("-1", None), ("bad", None)],
)
def test_processing_units_are_not_invented(
    settings: Settings, header: str | None, expected: float | None
) -> None:
    headers = {settings.access.processing_units_header: header} if header is not None else {}
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, headers=headers))
    ) as client:
        transport = Transport(client, settings.access, 1)
        transport.request("GET", "https://provider.invalid/", provider="test", operation="test")
    assert transport.observations[0].processing_units == expected


@pytest.mark.parametrize(
    "status,code", [(401, "authentication_failed"), (403, "access_denied"), (404, "http_404")]
)
def test_error_body_not_in_exception(settings: Settings, status: int, code: str) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, text="secret-value"))
    ) as client:
        transport = Transport(client, settings.access, 3)
        with pytest.raises(ProviderError, match=code) as error:
            transport.request("GET", "https://provider.invalid/", provider="test", operation="test")
    assert "secret-value" not in str(error.value)


def test_response_limit(settings: Settings) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"too-large"))
    ) as client:
        transport = Transport(client, settings.access, 1)
        with pytest.raises(ProviderError, match="response_size_limit"):
            transport.request(
                "GET", "https://provider.invalid/", provider="test", operation="test", max_bytes=1
            )


def test_signed_asset_urls_are_redacted() -> None:
    asset = Asset(key="blue", href="https://example.invalid/blue.tif?sig=secret#fragment")
    assert "secret" not in asset.model_dump_json()
    assert "secret" not in repr(asset)
    assert "secret" in asset.href


def test_token_is_cached_and_never_in_credentials_repr(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "allyourbase.providers.auth.load_credentials", lambda *args: Credentials("client", "secret")
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"access_token": "secret-token", "expires_in": 3600})

    provider = settings.providers.definitions["cdse_sentinelhub"]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        auth = TokenProvider("test", provider, Transport(client, settings.access, 1))
        assert auth.headers() == {"Authorization": "Bearer secret-token"}
        assert auth.headers() == {"Authorization": "Bearer secret-token"}
    assert len(requests) == 1
    assert "secret" not in repr(Credentials("client", "secret"))


def test_invalid_json_response(settings: Settings) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="secret-token-not-json"))
    ) as client:
        transport = Transport(client, settings.access, 1)
        with pytest.raises(ProviderError, match="invalid_json_response"):
            transport.json("GET", "https://provider.invalid/", provider="test", operation="test")


def test_compressed_response_is_decoded_once(settings: Settings) -> None:
    encoded = gzip.compress(b'{"ok": true}')
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=encoded, headers={"Content-Encoding": "gzip"})
        )
    ) as client:
        transport = Transport(client, settings.access, 1)
        assert transport.json(
            "GET", "https://provider.invalid/", provider="test", operation="test"
        ) == {"ok": True}
