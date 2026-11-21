"""Starts the app. Chooses stub or real services from ITSM_MODE (default: real).

Run:  uvicorn app.main:app --reload
Stub: ITSM_MODE=stub uvicorn app.main:app --reload

P4 adds routers below with two-line edits (import + include_router).
"""
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings
from app.ports.container import Container


def build_container(settings: Settings) -> Container:
    if settings.ITSM_MODE == "stub":
        from app.web.stubs.wiring import build_stub_container
        return build_stub_container()
    from app.services.wiring import build_real_container
    return build_real_container(settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="I-ITSM")
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
    app.state.settings = settings
    app.state.container = build_container(settings)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "mode": settings.ITSM_MODE}

    from app.web.setup import install_web
    install_web(app)
    return app


app = create_app()
