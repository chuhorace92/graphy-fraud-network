import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from graphy.api.v1 import (
    analytics,
    audit,
    cases,
    entities,
    graph,
    health,
    ingestion,
    me,
    resolution,
    search,
    views,
)
from graphy.config import get_settings
from graphy.db.neo4j import async_driver
from graphy.db.postgres import async_engine
from graphy.services.audit import request_id_var


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await async_driver().close()
    await async_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    app = FastAPI(
        title="Graphy",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id(request: Request,
                         call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid[:64])
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid[:64]
        return response

    v1 = APIRouter(prefix="/api/v1")
    for module in (health, resolution, entities, graph, search, analytics, ingestion, audit,
                   views, me, cases):
        v1.include_router(module.router)
    app.include_router(v1)
    return app


app = create_app()
