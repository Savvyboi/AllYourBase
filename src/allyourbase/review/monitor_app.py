"""Local category management for the monitor's configured sites."""

from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import Field

from allyourbase.models.common import Contract, Slug
from allyourbase.monitor.sites import SitesChanged, SiteStore
from allyourbase.review.local import create_local_app


class CategoryUpdate(Contract):
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    assignments: Annotated[dict[Slug, str], Field(min_length=1, max_length=10000)]


def register_monitor_routes(
    app: FastAPI, sites_path: Path, token: str, *, home: bool = False
) -> None:
    store = SiteStore(sites_path)

    def page() -> str:
        return (
            Path(__file__)
            .with_name("monitor.html")
            .read_text(encoding="utf-8")
            .replace("SESSION_TOKEN", token)
        )

    app.add_api_route("/monitor", page, response_class=HTMLResponse)
    if home:
        app.add_api_route("/", page, response_class=HTMLResponse)

    @app.get("/api/monitor/sites")
    def sites() -> dict[str, Any]:
        return store.snapshot()

    @app.post("/api/monitor/categories")
    def categories(body: CategoryUpdate) -> dict[str, Any]:
        try:
            return store.categorize(body.assignments, body.revision)
        except SitesChanged as exc:
            raise HTTPException(409, str(exc)) from None


def create_app(sites_path: Path) -> FastAPI:
    app, token = create_local_app("invalid site categories")
    register_monitor_routes(app, sites_path, token, home=True)
    return app
