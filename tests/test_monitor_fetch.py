import io
import json
import shutil
import subprocess
import tarfile
from datetime import date
from pathlib import Path

import httpx
import pytest

from allyourbase.monitor.config import Location, MonitorConfig, make_grid, windows
from allyourbase.monitor.fetch import Fetcher, LimitedTransport, process_request, read_pixels
from allyourbase.monitor.main import SyntheticImagery
from allyourbase.providers.auth import Credentials
from allyourbase.providers.contracts import Acquisition, ProviderError


def scene(sensor: str = "s2") -> Acquisition:
    grid = make_grid(Location(id="test", name="Fictional", latitude=0, longitude=0))
    return SyntheticImagery(date(2020, 10, 12), True).discover(
        grid, sensor, *windows(date(2020, 10, 12))[::2]
    )[-1]


def tiff(sensor: str = "s2", bad_transform: bool = False) -> bytes:
    from rasterio.io import MemoryFile

    grid = make_grid(Location(id="test", name="Fictional", latitude=0, longitude=0))
    pixels = SyntheticImagery(date(2020, 10, 12), True).cutout(scene(sensor), grid).pixels
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=100,
            height=100,
            count=len(pixels),
            dtype="float32",
            crs=grid.epsg,
            transform=grid.transform @ grid.transform.translation(1, 0)
            if bad_transform
            else grid.transform,
        ) as dataset:
            dataset.write(pixels)
        return bytes(memory.read())


def response_archive(sensor: str = "s2", wrong_scene: bool = False) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, content in [
            ("data.tif", tiff(sensor)),
            (
                "userdata.json",
                json.dumps(
                    {"scene_ids": ["wrong" if wrong_scene else scene(sensor).scene_id]}
                ).encode(),
            ),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def test_process_contract_scene_isolation_and_evalscript(monitor_config: MonitorConfig) -> None:
    grid = make_grid(Location(id="test", name="Fictional", latitude=0, longitude=0))
    for sensor in ("s1", "s2"):
        request = process_request(scene(sensor), grid, monitor_config)
        assert request["output"]["width"] == request["output"]["height"] == 100
        assert request["input"]["bounds"]["bbox"] == list(grid.bbox)
        processing = request["input"]["data"][0]["processing"]
        if sensor == "s1":
            assert processing["backCoeff"] == "GAMMA0_TERRAIN"
            assert processing["orthorectify"] is True
            assert processing["demInstance"] == "COPERNICUS_30"
            assert processing["speckleFilter"] == {
                "type": "LEE",
                "windowSizeX": 3,
                "windowSizeY": 3,
            }
        else:
            assert processing["upsampling"] == processing["downsampling"] == "NEAREST"
            assert "REFLECTANCE" in request["evalscript"]
        if shutil.which("node"):
            key = "sentinel1ProductId" if sensor == "s1" else "sentinel2ProductId"
            code = request["evalscript"] + (
                "\nconst m={};updateOutputMetadata({orbits:[{tiles:[{"
                + key
                + ":"
                + json.dumps(scene(sensor).scene_id)
                + "}]}]},null,m);console.log(JSON.stringify([m.userData.scene_ids,"
                "evaluatePixel([{},{}])]));"
            )
            result = subprocess.run(
                ["node", "-e", code], capture_output=True, text=True, check=True
            )
            identifiers, zero = json.loads(result.stdout)
            assert identifiers == [scene(sensor).scene_id] and set(zero) == {0}


def test_cache_hit_verifies_hash_and_never_repeats_process(
    monitor_config: MonitorConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "allyourbase.providers.auth.load_credentials",
        lambda *_: Credentials("fixture-id", "fixture-secret"),
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "fixture-token", "expires_in": 3600})
        return httpx.Response(200, content=response_archive())

    fetcher = Fetcher(
        monitor_config, tmp_path, httpx.Client(transport=httpx.MockTransport(handler))
    )
    grid = make_grid(Location(id="test", name="Fictional", latitude=0, longitude=0))
    first = fetcher.cutout(scene(), grid)
    fetcher.cutout(scene(), grid)
    assert len(calls) == 2 and first.pixels.shape == (6, 100, 100)
    next(tmp_path.rglob("data.tif")).write_bytes(b"changed")
    with pytest.raises(ProviderError, match="cache_integrity"):
        fetcher.cutout(scene(), grid)
    assert len(calls) == 2


@pytest.mark.parametrize("kind", ["wrong_scene", "bad_archive", "ambiguous_failure"])
def test_bad_process_result_or_ambiguous_charge_is_not_cached_or_retried(
    kind: str, monitor_config: MonitorConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "allyourbase.providers.auth.load_credentials",
        lambda *_: Credentials("fixture-id", "fixture-secret"),
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "fixture-token", "expires_in": 3600})
        if kind == "ambiguous_failure":
            raise httpx.ReadTimeout("secret response details")
        return httpx.Response(
            200,
            content=b"not-a-tar" if kind == "bad_archive" else response_archive(wrong_scene=True),
        )

    fetcher = Fetcher(
        monitor_config, tmp_path, httpx.Client(transport=httpx.MockTransport(handler))
    )
    grid = make_grid(Location(id="test", name="Fictional", latitude=0, longitude=0))
    with pytest.raises((ValueError, ProviderError)) as error:
        fetcher.cutout(scene(), grid)
    assert "secret response details" not in str(error.value)
    assert len(calls) == 2 and not list(tmp_path.rglob("data.tif"))
    if kind == "wrong_scene":
        with pytest.raises(ProviderError, match="scene_selection_mismatch"):
            fetcher.cutout(scene(), grid)
        assert len(calls) == 2  # Known rejected selection is never charged twice.


def test_every_retry_counts_against_request_cap(monitor_config: MonitorConfig) -> None:
    calls = []
    config = monitor_config.model_copy(update={"max_requests": 2})

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429)

    transport = LimitedTransport(httpx.Client(transport=httpx.MockTransport(handler)), config)
    transport.sleep = lambda _: None
    with pytest.raises(ProviderError, match="http_429"):
        transport.request("POST", "https://example.invalid", provider="test", operation="discovery")
    with pytest.raises(ProviderError, match="request_cap"):
        transport.request("POST", "https://example.invalid", provider="test", operation="discovery")
    assert len(calls) == 2 and transport.remaining == 0


def test_unknown_relative_orbit_never_requests_pixels(
    monitor_config: MonitorConfig, tmp_path: Path
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    fetcher = Fetcher(
        monitor_config, tmp_path, httpx.Client(transport=httpx.MockTransport(handler))
    )
    grid = make_grid(Location(id="test", name="Fictional", latitude=0, longitude=0))
    with pytest.raises(ProviderError, match="geometry_unverified"):
        fetcher.cutout(scene("s1").model_copy(update={"relative_orbit": None}), grid)
    assert not calls


def test_shifted_grid_is_rejected() -> None:
    grid = make_grid(Location(id="test", name="Fictional", latitude=0, longitude=0))
    with pytest.raises(ValueError, match="transform"):
        read_pixels(tiff(bad_transform=True), grid, "s2")
