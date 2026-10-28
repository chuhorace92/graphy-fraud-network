"""Background jobs, run inside the API process after the response is sent (TRD 7).

Long operations return 202 with a job id; each job updates its job_run row, so the UI can
show status and counts. A job is lost if the API restarts while it runs, and its row stays
"running". Loading and resolution are idempotent, so submit the batch again.
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from graphy.auth import User
from graphy.catalog import ENTITY_TYPES, load_catalog
from graphy.config import get_settings
from graphy.db.models import JobRun
from graphy.db.neo4j import sync_driver
from graphy.db.postgres import sync_session
from graphy.ingestion.loader import load_json, load_relationships, load_rows, read_csv
from graphy.resolution.aliases import rebuild_related
from graphy.resolution.deterministic import rebuild_shares, resolve_entity_type
from graphy.services.audit import record_sync

MAX_REJECTS_KEPT = 1000


class JobAccepted(BaseModel):
    job_id: str
    status: str = "queued"


def create_job(kind: str, params: dict[str, Any], created_by: str) -> str:
    """Returns the id as a string, as the API hands it out."""
    with sync_session() as pg:
        job = JobRun(kind=kind, params=params, created_by=created_by)
        pg.add(job)
        pg.commit()
        return str(job.id)


async def enqueue(pg: AsyncSession, user: User, background: BackgroundTasks, kind: str,
                  params: dict[str, Any], run: Callable[..., None], *args: Any) -> JobAccepted:
    """Record the job, then run `run(job_id, *args)` once the response has gone out."""
    job = JobRun(kind=kind, params=params, created_by=user.subject)
    pg.add(job)
    await pg.commit()  # the job must be readable by its id before it starts
    background.add_task(run, str(job.id), *args)
    return JobAccepted(job_id=str(job.id))


@contextmanager
def tracked(job_id: str) -> Iterator[dict[str, Any]]:
    """Mark the job running, then succeeded or failed. Yields a dict the job fills with counts."""
    counts: dict[str, Any] = {}
    with sync_session() as pg:
        job = pg.get(JobRun, uuid.UUID(job_id))
        if job is None:
            raise LookupError(f"job_run {job_id} not found")
        job.status, job.started_at, job.error = "running", datetime.now(UTC), None
        pg.commit()
        try:
            yield counts
        except Exception as exc:
            pg.rollback()
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
            raise
        else:
            job.status = "succeeded"
        finally:
            job.counts, job.finished_at = counts, datetime.now(UTC)
            pg.commit()


def ingest_batch(job_id: str, data: bytes, is_json: bool) -> None:
    """Load an uploaded batch, then resolve unless the job asked not to. Rejected rows (never
    their values) are kept on the job, up to MAX_REJECTS_KEPT."""
    settings = get_settings()
    with tracked(job_id) as counts, sync_session() as pg:
        job = pg.get(JobRun, uuid.UUID(job_id))
        assert job is not None
        params = job.params
        if is_json:
            result = load_json(data, source_system=params["source_system"], batch_id=job_id,
                               catalog=load_catalog(pg), driver=sync_driver(), settings=settings)
        else:
            rows = read_csv(data)
            load = load_relationships if rows and "from_key" in rows[0] else load_rows
            result = load(
                rows, source_system=params["source_system"], batch_id=job_id,
                catalog=load_catalog(pg), driver=sync_driver(), settings=settings,
            )
        counts.update(result.counts())
        counts["rejects"] = result.rejects[:MAX_REJECTS_KEPT]

    if params.get("resolve_after", True):
        resolve(create_job("resolution", {"trigger": f"batch:{job_id}"}, "system"))


def ingest_rows_now(job_id: str, rows: list[dict[str, str]],
                    source_system: str) -> dict[str, Any]:
    """Load already-parsed rows in-process (seeding and tests)."""
    settings = get_settings()
    with tracked(job_id) as counts, sync_session() as pg:
        load = load_relationships if rows and "from_key" in rows[0] else load_rows
        result = load(rows, source_system=source_system, batch_id=job_id,
                      catalog=load_catalog(pg), driver=sync_driver(), settings=settings)
        counts.update(result.counts())
    return counts


def resolve(job_id: str) -> None:
    settings = get_settings()
    with tracked(job_id) as counts, sync_session() as pg:
        for entity_type in ENTITY_TYPES:
            stats = resolve_entity_type(entity_type=entity_type, run_id=job_id,
                                        driver=sync_driver(), pg=pg, settings=settings)
            counts[entity_type] = stats.counts()
        counts["shares"] = rebuild_shares(driver=sync_driver(), catalog=load_catalog(pg),
                                          settings=settings)
        counts["related"] = rebuild_related(driver=sync_driver(), settings=settings)
        record_sync(pg, "system", "resolution.run", "job_run", job_id, after=counts)
        pg.commit()
