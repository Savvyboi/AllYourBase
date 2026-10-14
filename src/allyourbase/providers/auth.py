"""Credentials from environment or OS keychain; tokens remain in memory."""

import os
import time
from dataclasses import dataclass

from allyourbase.models.settings import Provider
from allyourbase.providers.contracts import ProviderError
from allyourbase.providers.http import Transport


@dataclass(frozen=True, repr=False)
class Credentials:
    client_id: str
    client_secret: str


def load_credentials(provider: Provider, service: str) -> Credentials | None:
    if not provider.client_id_env or not provider.client_secret_env:
        return None
    client_id = os.environ.get(provider.client_id_env)
    secret = os.environ.get(provider.client_secret_env)
    if not client_id or not secret:
        try:
            import keyring

            client_id = client_id or keyring.get_password(service, provider.client_id_env)
            secret = secret or keyring.get_password(service, provider.client_secret_env)
        except Exception:
            # A missing/locked backend is an availability state, not a reason to log secrets.
            return None
    if not client_id or not secret:
        return None
    return Credentials(client_id, secret)


class TokenProvider:
    def __init__(self, provider_id: str, provider: Provider, transport: Transport) -> None:
        self.provider_id = provider_id
        self.provider = provider
        self.transport = transport
        self._token: str | None = None
        self._expires_at = 0.0

    def headers(self) -> dict[str, str]:
        if self._token is None or time.monotonic() >= self._expires_at:
            credentials = load_credentials(self.provider, self.transport.settings.keyring_service)
            if credentials is None:
                raise ProviderError("credentials_missing", self.provider_id)
            data = self.transport.json(
                "POST",
                str(self.provider.token_url),
                provider=self.provider_id,
                operation="oauth",
                form={
                    "grant_type": "client_credentials",
                    "client_id": credentials.client_id,
                    "client_secret": credentials.client_secret,
                },
            )
            token = data.get("access_token")
            expires = data.get("expires_in")
            if not isinstance(token, str) or not isinstance(expires, (int, float)) or expires <= 0:
                raise ProviderError("invalid_token_response", self.provider_id)
            self._token = token
            self._expires_at = (
                time.monotonic() + expires * self.transport.settings.token_refresh_fraction
            )
        return {"Authorization": f"Bearer {self._token}"}
