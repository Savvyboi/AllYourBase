"""Loopback-only catalogue review with session-token protected API access."""

import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from allyourbase.catalogue.review import ReviewBundle, accept
from allyourbase.loading import InputError
from allyourbase.project import Project
from allyourbase.sources.store import Store


def create_app(project: Project) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    token = secrets.token_urlsafe(32)
    store = Store(project.workspace)

    @app.middleware("http")
    async def local_only(request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"error": "loopback host required"}, status_code=403)
        if request.url.path.startswith("/api/"):
            if not secrets.compare_digest(request.headers.get("x-review-token", ""), token):
                return JSONResponse({"error": "review session token required"}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"error": "same-origin request required"}, status_code=403)
        result = await call_next(request)
        result.headers["Cache-Control"] = "no-store"
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'none'"
        )
        return result

    @app.exception_handler(InputError)
    async def input_error(request: Request, exc: InputError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": "invalid catalogue bundle",
                "fields": [list(e["loc"]) for e in exc.errors(include_input=False)],
            },
            status_code=400,
        )

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
