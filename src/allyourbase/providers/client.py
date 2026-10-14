"""One discovery/window-read interface keeps source changes outside analysis code."""

from datetime import datetime
from pathlib import Path
from typing import Any

from allyourbase.models.geometry import Geometry
from allyourbase.models.settings import Settings
from allyourbase.providers.budget import BudgetLedger
from allyourbase.providers.contracts import Acquisition, ProviderError
from allyourbase.providers.http import Transport
from allyourbase.providers.pixels import read_optical_windows
from allyourbase.providers.radar import fetch_radar_window
from allyourbase.providers.stac import STACProvider


class ProviderClient:
    def __init__(
        self, provider_id: str, settings: Settings, transport: Transport, ledger: BudgetLedger
    ) -> None:
        self.provider_id = provider_id
        self.settings = settings
        self.config = settings.providers.definitions[provider_id]
        self.transport = transport
        self.ledger = ledger
        self.discovery = STACProvider(provider_id, self.config, transport)

    def discover(self, geometry: Geometry, start: datetime, end: datetime) -> list[Acquisition]:
        return self.discovery.discover(geometry, start, end)

    def read_window(
        self, acquisition: Acquisition, geometry: Geometry, directory: Path
    ) -> dict[str, Any]:
        if (
            acquisition.provider != self.provider_id
            or acquisition.collection != self.config.collection
        ):
            raise ProviderError("scene_provider_mismatch", self.provider_id)
        if self.config.sensor == "s2":
            return {
                "files": read_optical_windows(
                    acquisition,
                    geometry,
                    self.config,
                    self.settings,
                    directory,
                )
            }
        if self.config.kind != "sentinelhub":
            raise ProviderError("rtc_pixels_not_implemented", self.provider_id)
        return {
            "files": [
                fetch_radar_window(
                    acquisition,
                    geometry,
                    self.config,
                    self.settings,
                    self.transport,
                    self.ledger,
                    directory,
                    auth=self.discovery.auth,
                )
            ]
        }
