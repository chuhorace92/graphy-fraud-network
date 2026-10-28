import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from graphy.api.deps import Admin, Pg, Reader
from graphy.db.models import IngestionSource, JobRun
from graphy.schemas.ingestion import BatchIn
from graphy.services import audit
from graphy.services.jobs import JobAccepted, enqueue, ingest_batch

router = APIRouter(tags=["ingestion"])

MAX_UPLOAD_BYTES = 512 * 1024 * 1024


class SourceIn(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,127}$")
    source_system: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    description: str | None = None


class SourceOut(SourceIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    params: dict[str, Any]
    counts: dict[str, Any]
    error: str | None
    created_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@router.get("/ingestion/sources", response_model=list[SourceOut])
async def list_sources(pg: Pg, _: Reader) -> list[IngestionSource]:
    return list(await pg.scalars(select(IngestionSource).order_by(IngestionSource.name)))


@router.post("/ingestion/sources", response_model=SourceOut, status_code=201)
async def create_source(body: SourceIn, pg: Pg, user: Admin) -> IngestionSource:
    source = IngestionSource(**body.model_dump())
    pg.add(source)
    try:
        await pg.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "A source with this name already exists") from exc
    await audit.record(pg, user, "source.create", "ingestion_source", str(source.id),
                       after=body.model_dump())
    await pg.commit()
    return source


@router.post("/ingestion/batches", response_model=JobAccepted, status_code=202)
async def submit_batch(
    pg: Pg, user: Admin, background: BackgroundTasks,
    source: str = Form(),
    file: UploadFile = File(),
    resolve_after: bool = Form(True),
) -> JobAccepted:
    """Accept a canonical CSV and load it in the background (X-1)."""
    src = await pg.scalar(select(IngestionSource).where(IngestionSource.name == source))
    if src is None:
        raise HTTPException(404, f"Unknown source {source!r}")
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")

    accepted = await enqueue(pg, user, background, "ingestion", {
        "source": src.name, "source_system": src.source_system, "resolve_after": resolve_after,
    }, ingest_batch, await file.read(), False)
    await audit.record(pg, user, "batch.submit", "job_run", accepted.job_id,
                       after={"source": src.name})
    await pg.commit()
    return accepted


@router.post("/ingestion/batches/json", response_model=JobAccepted, status_code=202)
async def submit_json_batch(body: BatchIn, pg: Pg, user: Admin,
                            background: BackgroundTasks) -> JobAccepted:
    """Accept records and relationships as JSON and load them in the background.

    The shape is checked here; attribute types, values and relationship ends are validated by
    the loader, and anything it rejects is listed in the job's counts."""
    src = await pg.scalar(select(IngestionSource).where(IngestionSource.name == body.source))
    if src is None:
        raise HTTPException(404, f"Unknown source {body.source!r}")
    accepted = await enqueue(pg, user, background, "ingestion", {
        "source": src.name, "source_system": src.source_system,
        "resolve_after": body.resolve_after,
    }, ingest_batch, body.model_dump_json().encode(), True)
    await audit.record(pg, user, "batch.submit", "job_run", accepted.job_id,
                       after={"source": src.name, "format": "json"})
    await pg.commit()
    return accepted


@router.get("/ingestion/batches/{job_id}", response_model=JobOut)
@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, pg: Pg, _: Reader) -> JobRun:
    job = await pg.get(JobRun, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(pg: Pg, _: Reader, kind: str | None = None, limit: int = 50) -> list[JobRun]:
    q = select(JobRun).order_by(JobRun.created_at.desc()).limit(min(limit, 200))
    if kind:
        q = q.where(JobRun.kind == kind)
    return list(await pg.scalars(q))
