"""Native-grid AOI window reads for the access spike, not Phase 3 preprocessing."""

import hashlib
import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from shapely.geometry import shape

from allyourbase.models.geometry import Geometry
from allyourbase.models.settings import Provider, Settings
from allyourbase.providers.contracts import Acquisition, ProviderError, public_url
from allyourbase.providers.spatial import query_parts


def _environment(provider: Provider, href: str) -> dict[str, Any]:
    if urlsplit(href).scheme != "s3":
        return {}
    if provider.s3_endpoint is None:
        return {"AWS_NO_SIGN_REQUEST": "YES"}
    access_key = os.environ.get(provider.s3_access_key_env or "")
    secret_key = os.environ.get(provider.s3_secret_key_env or "")
    if not access_key or not secret_key:
        raise ProviderError("s3_credentials_missing", "optical")
    import boto3
    from rasterio.session import AWSSession

    session = boto3.Session(
        aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name="default"
    )
    return {
        "session": AWSSession(session),
        "AWS_S3_ENDPOINT": urlsplit(str(provider.s3_endpoint)).netloc,
        "AWS_VIRTUAL_HOSTING": False,
        "AWS_HTTPS": True,
    }


def read_optical_windows(
    acquisition: Acquisition,
    geometry: Geometry,
    provider: Provider,
    settings: Settings,
    directory: Path,
) -> list[dict[str, Any]]:
    try:
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.windows import Window, from_bounds
    except ImportError:
        raise ProviderError("access_extra_required", acquisition.provider) from None
    if acquisition.sensor != "s2":
        raise ProviderError("optical_scene_required", acquisition.provider)
    assets = {asset.key: asset for asset in acquisition.assets}
    selected = []
    for band in settings.preprocessing.optical_bands:
        keys = provider.band_assets.get(band.lower(), [])
        asset = next((assets[key] for key in keys if key in assets), None)
        if asset is None:
            raise ProviderError(f"band_asset_missing_{band.lower()}", acquisition.provider)
        selected.append((band, asset))
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(acquisition.scene_id.encode()).hexdigest()
    outputs = []
    for band, asset in selected:
        # Resolve local paths before URL parsing, including Windows drive letters.
        scheme = "" if Path(asset.href).is_file() else urlsplit(asset.href).scheme
        if scheme not in {"http", "https", "s3", ""}:
            raise ProviderError("unsupported_asset_scheme", acquisition.provider)
        if scheme == "" and not Path(asset.href).is_file():
            raise ProviderError("asset_unavailable", acquisition.provider)
        options = _environment(provider, asset.href)
        # Avoid auxiliary directory listings and whole-tile reads on remote COGs.
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", **options):
            try:
                with rasterio.open(asset.href) as source:
                    if source.crs is None:
                        raise ProviderError("asset_crs_missing", acquisition.provider)
                    for part_id, part in enumerate(query_parts(geometry)):
                        bounds = transform_bounds("EPSG:4326", source.crs, *shape(part).bounds)
                        raw = from_bounds(*bounds, transform=source.transform)
                        left, top = math.floor(raw.col_off), math.floor(raw.row_off)
                        right, bottom = (
                            math.ceil(raw.col_off + raw.width),
                            math.ceil(raw.row_off + raw.height),
                        )
                        window = Window(left, top, right - left, bottom - top).intersection(
                            Window(0, 0, source.width, source.height)
                        )
                        if window.width * window.height > settings.access.max_window_pixels:
                            raise ProviderError("window_pixel_limit", acquisition.provider)
                        pixels = source.read(1, window=window)
                        transform = source.window_transform(window)
                        filename = f"{digest}_{band}_{part_id}.tif"
                        path = directory / filename
                        temporary = directory / f".{filename}.tmp"
                        profile = {
                            "driver": "GTiff",
                            "height": pixels.shape[0],
                            "width": pixels.shape[1],
                            "count": 1,
                            "dtype": pixels.dtype,
                            "crs": source.crs,
                            "transform": transform,
                            "nodata": source.nodata,
                            "compress": "deflate",
                        }
                        with rasterio.open(temporary, "w", **profile) as output:
                            output.write(pixels, 1)
                            output.set_band_description(1, band)
                        temporary.replace(path)
                        outputs.append(
                            {
                                "provider": acquisition.provider,
                                "scene_id": acquisition.scene_id,
                                "band": band,
                                "part": part_id,
                                "file": filename,
                                "source": public_url(asset.href),
                                "source_media_type": asset.media_type,
                                "crs": str(source.crs),
                                "width": pixels.shape[1],
                                "height": pixels.shape[0],
                                "pixel_size": [abs(transform.a), abs(transform.e)],
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            }
                        )
            except ProviderError:
                raise
            except Exception:
                raise ProviderError("window_read_failed", acquisition.provider) from None
    return outputs
