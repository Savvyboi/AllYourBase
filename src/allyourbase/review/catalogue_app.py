"""Loopback-only catalogue review with session-token protected API access."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from allyourbase.catalogue.review import ReviewBundle, accept
from allyourbase.loading import InputError
from allyourbase.project import Project
from allyourbase.sources.store import Store


def create_app(project: Project) -> FastAPI:
    from allyourbase.review.local import create_local_app
    from allyourbase.review.monitor_app import register_monitor_routes

    app, token = create_local_app("invalid catalogue bundle")
    store = Store(project.workspace)
    register_monitor_routes(app, project.root / "sites.yaml", token)

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return (
            Path(__file__)
            .with_name("catalogue.html")
            .read_text(encoding="utf-8")
            .replace("SESSION_TOKEN", token)
        )

    @app.get("/api/queue")
    def queue(state: str = "pending") -> list[dict[str, Any]]:
        if state not in {"pending", "accepted", "rejected", "superseded"}:
            raise HTTPException(400, "invalid state")
        return store.proposals(state)

    @app.get("/api/proposal/{identifier}")
    def proposal(identifier: str) -> dict[str, Any]:
        return store.proposal(identifier)

    @app.post("/api/preview")
    def preview(bundle: ReviewBundle) -> dict[str, Any]:
        return {"sites": [site.model_dump(mode="json") for site in bundle.sites]}

    @app.post("/api/decision/{identifier}")
    def decision(identifier: str, body: dict[str, Any]) -> dict[str, Any]:
        reviewer, note = str(body.get("reviewer", "")), str(body.get("note", ""))
        action = body.get("action")
        if action == "reject":
            store.decide(identifier, "rejected", reviewer, note)
            return {"state": "rejected"}
        if action not in {"validate", "accept"}:
            raise InputError("unknown review action")
        bundle = ReviewBundle.model_validate(body.get("bundle"))
        return accept(project, identifier, bundle, reviewer, note, dry_run=action == "validate")

    return app
