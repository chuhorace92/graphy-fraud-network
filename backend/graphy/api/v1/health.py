import asyncio

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from graphy.db.neo4j import async_driver
from graphy.db.postgres import async_engine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """Liveness: the process is up. Never touches dependencies."""
    return {"status": "ok"}


async def _postgres() -> None:
    async with async_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _neo4j() -> None:
    await async_driver().verify_connectivity()


@router.get("/ready")
async def ready(response: Response) -> dict[str, object]:
    """Readiness: all backing stores answer within two seconds."""
    checks = {"postgres": _postgres, "neo4j": _neo4j}
    results: dict[str, str] = {}
    for name, check in checks.items():
        try:
            await asyncio.wait_for(check(), timeout=2)
            results[name] = "ok"
        except Exception as exc:  # noqa: BLE001 - report any failure as not ready
            results[name] = f"error: {type(exc).__name__}"
    ok = all(v == "ok" for v in results.values())
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ok else "degraded", "checks": results}
