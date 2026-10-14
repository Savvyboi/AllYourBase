import io
import json
import tarfile
from pathlib import Path

import httpx
import numpy as np
import pytest

from allyourbase.models.geometry import Polygon
from allyourbase.models.settings import Settings
from allyourbase.providers.auth import Credentials
from allyourbase.providers.budget import BudgetLedger
from allyourbase.providers.contracts import Acquisition, Asset, ProviderError
from allyourbase.providers.http import Transport
from allyourbase.providers.pixels import read_optical_windows
from allyourbase.providers.radar import fetch_radar_window, radar_request, site_grid

rasterio = pytest.importorskip("rasterio")
pytest.importorskip("pyproj")
MemoryFile = rasterio.io.MemoryFile
from_origin = rasterio.transform.from_origin


def small_aoi(longitude: float = 0, latitude: float = 0) -> Polygon:
    size = 0.001
    return Polygon.model_validate(
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [longitude, latitude],
                    [longitude + size, latitude],
                    [longitude + size, latitude + size],
                    [longitude, latitude + size],
                    [longitude, latitude],
                ]
            ],
        }
    )


def radar_scene(polarisations: tuple[str, ...] = ("VV", "VH")) -> Acquisition:
    return Acquisition.model_validate(
        {
            "provider": "cdse_sentinelhub",
            "collection": "sentinel-1-grd",
            "scene_id": "synthetic-radar-scene",
            "sensor": "s1",
            "acquired_at": "2020-12-30T12:00:00Z",
            "orbit_direction": "ascending",
            "relative_orbit": 17,
            "instrument_mode": "IW",
            "polarisations": polarisations,
        }
    )


def test_optical_read_is_a_window_with_georeferencing(tmp_path: Path, settings: Settings) -> None:
    source = tmp_path / "source.tif"
    pixels = np.arange(10000, dtype="uint16").reshape(100, 100)
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        height=100,
        width=100,
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(0, 0.1, 0.001, 0.001),
    ) as output:
        output.write(pixels, 1)
    provider = settings.providers.definitions["earth_search"]
    settings.preprocessing.optical_bands = ["B02"]
    scene = Acquisition.model_validate(
        {
            "provider": "earth_search",
            "collection": provider.collection,
            "scene_id": "synthetic-optical-scene",
            "sensor": "s2",
            "acquired_at": "2020-12-30T12:00:00Z",
            "assets": [Asset(key="blue", href=str(source))],
        }
    )
    metadata = read_optical_windows(
        scene, small_aoi(0.02, 0.02), provider, settings, tmp_path / "chips"
    )
    with rasterio.open(tmp_path / "chips" / metadata[0]["file"]) as chip:
        assert chip.width <= 2 and chip.height <= 2
        assert chip.crs.to_epsg() == 4326
        assert chip.transform.a == 0.001
        assert chip.read(1).size < pixels.size
    assert metadata[0]["scene_id"] == scene.scene_id


def test_missing_band_has_explicit_error(tmp_path: Path, settings: Settings) -> None:
    provider = settings.providers.definitions["earth_search"]
    scene = Acquisition.model_validate(
        {
            "provider": "earth_search",
            "collection": provider.collection,
            "scene_id": "synthetic-optical-scene",
            "sensor": "s2",
            "acquired_at": "2020-12-30T12:00:00Z",
        }
    )
    with pytest.raises(ProviderError, match="band_asset_missing"):
        read_optical_windows(scene, small_aoi(), provider, settings, tmp_path / "chips")


@pytest.mark.parametrize(
    "longitude,latitude,expected", [(0, 0, 32631), (0, -30, 32731), (0, 85, 3413), (0, -85, 3031)]
)
def test_grid_hemispheres_and_poles(
    settings: Settings, longitude: float, latitude: float, expected: int
) -> None:
    grid = site_grid(small_aoi(longitude, latitude), settings)
    assert grid["epsg"] == expected
    assert grid["resolution_m"] == 10


@pytest.mark.parametrize(
    "polarisations,bands", [(("VV", "VH"), ("VV", "VH")), (("HH", "HV"), ("HH", "HV"))]
)
def test_radar_request_contract(
    settings: Settings, polarisations: tuple[str, ...], bands: tuple[str, ...]
) -> None:
    request = radar_request(
        radar_scene(polarisations),
        small_aoi(),
        settings.providers.definitions["cdse_sentinelhub"],
        settings,
    )
    processing = request["input"]["data"][0]["processing"]
    assert processing == {
        "backCoeff": "GAMMA0_TERRAIN",
        "orthorectify": True,
        "demInstance": "COPERNICUS_30",
    }
    for band in [*bands, "shadowMask", "dataMask"]:
        assert band in request["evalscript"]
    assert "FLOAT32" in request["evalscript"]


def radar_response(
    scene_id: str,
    geometry: Polygon,
    settings: Settings,
    shift_x: float = 0,
    metadata: object | None = None,
    mask_value: float = 1,
) -> bytes:
    grid = site_grid(geometry, settings)
    pixels = np.ones((4, grid["height"], grid["width"]), dtype="float32")
    pixels[2] = 0
    pixels[3] = mask_value
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            count=4,
            height=grid["height"],
            width=grid["width"],
            dtype="float32",
            crs=f"EPSG:{grid['epsg']}",
            transform=from_origin(grid["bbox"][0] + shift_x, grid["bbox"][3], 10, 10),
        ) as output:
            output.write(pixels)
        image = memory.read()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in [
            ("radar.tif", image),
            (
                "userdata.json",
                json.dumps({"scene_ids": [scene_id]} if metadata is None else metadata).encode(),
            ),
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return stream.getvalue()


@pytest.mark.parametrize(
    "scene_id,returned_id",
    [
        ("synthetic-radar-scene", "synthetic-radar-scene"),
        ("synthetic-radar-scene_COG.SAFE", "synthetic-radar-scene_COG.SAFE"),
        ("synthetic-radar-scene_COG.SAFE", "synthetic-radar-scene_COG"),
    ],
)
def test_radar_response_provenance_and_actual_cost(
    tmp_path: Path,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    scene_id: str,
    returned_id: str,
) -> None:
    monkeypatch.setattr(
        "allyourbase.providers.auth.load_credentials", lambda *args: Credentials("client", "secret")
    )
    scene = radar_scene().model_copy(update={"scene_id": scene_id})
    geometry = small_aoi()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("token"):
            return httpx.Response(200, json={"access_token": "secret-token", "expires_in": 3600})
        return httpx.Response(
            200,
            content=radar_response(returned_id, geometry, settings),
            headers={settings.access.processing_units_header: "1.25"},
        )

    ledger = BudgetLedger(tmp_path / "workspace", settings)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        transport = Transport(client, settings.access, 3)
        metadata = fetch_radar_window(
            scene,
            geometry,
            settings.providers.definitions["cdse_sentinelhub"],
            settings,
            transport,
            ledger,
            tmp_path / "chips",
        )
    assert metadata["scene_ids"] == [returned_id]
    assert metadata["requested_scene_id"] == scene_id
    assert metadata["processing_units"] == 1.25
    assert metadata["valid_pixels"] > 0
    assert json.loads(ledger.path.read_text())[0]["actual_pu"] == 1.25


def test_wrong_radar_scene_never_becomes_a_chip(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "allyourbase.providers.auth.load_credentials", lambda *args: Credentials("client", "secret")
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("token"):
            return httpx.Response(200, json={"access_token": "secret-token", "expires_in": 3600})
        return httpx.Response(200, content=radar_response("wrong-scene", small_aoi(), settings))

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProviderError, match="radar_scene_selection_mismatch"),
    ):
        fetch_radar_window(
            radar_scene(),
            small_aoi(),
            settings.providers.definitions["cdse_sentinelhub"],
            settings,
            Transport(client, settings.access, 1),
            BudgetLedger(tmp_path / "workspace", settings),
            tmp_path / "chips",
        )
    assert not (tmp_path / "chips").exists()


def test_shifted_radar_grid_is_rejected(
    tmp_path: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "allyourbase.providers.auth.load_credentials", lambda *args: Credentials("client", "secret")
    )
    scene = radar_scene()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(
            200, content=radar_response(scene.scene_id, small_aoi(), settings, shift_x=10)
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProviderError, match="radar_transform_mismatch"),
    ):
        fetch_radar_window(
            scene,
            small_aoi(),
            settings.providers.definitions["cdse_sentinelhub"],
            settings,
            Transport(client, settings.access, 1),
            BudgetLedger(tmp_path / "workspace", settings),
            tmp_path / "chips",
        )
    assert not (tmp_path / "chips").exists()


@pytest.mark.parametrize(
    "metadata,mask_value,code",
    [
        ([], 1, "invalid_radar_response"),
        ({"scene_ids": "synthetic-radar-scene"}, 1, "radar_scene_selection_mismatch"),
        ({"scene_ids": [12]}, 1, "radar_scene_selection_mismatch"),
        (None, 2, "radar_mask_contract_mismatch"),
    ],
)
def test_malformed_radar_response_keeps_charge_without_writing_chip(
    tmp_path: Path,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    metadata: object,
    mask_value: float,
    code: str,
) -> None:
    monkeypatch.setattr(
        "allyourbase.providers.auth.load_credentials",
        lambda *args: Credentials("client", "secret"),
    )
    scene = radar_scene()
    ledger = BudgetLedger(tmp_path / "workspace", settings)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        return httpx.Response(
            200,
            content=radar_response(
                scene.scene_id,
                small_aoi(),
                settings,
                metadata=metadata,
                mask_value=mask_value,
            ),
            headers={settings.access.processing_units_header: "1.25"},
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ProviderError, match=code),
    ):
        fetch_radar_window(
            scene,
            small_aoi(),
            settings.providers.definitions["cdse_sentinelhub"],
            settings,
            Transport(client, settings.access, 1),
            ledger,
            tmp_path / "chips",
        )
    assert not (tmp_path / "chips").exists()
    assert json.loads(ledger.path.read_text())[0]["actual_pu"] == 1.25
