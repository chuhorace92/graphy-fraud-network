import uuid
from collections.abc import Awaitable
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse

from graphy.api.deps import Graph, Investigator, Pg, Reader
from graphy.config import get_settings
from graphy.schemas.cases import (
    AgentStatus,
    CaseClaims,
    CaseClose,
    CaseDetail,
    CaseSummary,
    CaseUpdate,
    DocumentTag,
    NoteIn,
    NoteUpdate,
    Report,
    ReportDraft,
    TaskIn,
    TaskUpdate,
)
from graphy.services import agent, cases

router = APIRouter(prefix="/cases", tags=["cases"])


async def _detail(graph: Graph, pg: Pg, key: str) -> CaseDetail:
    result = await cases.get_case(graph, pg, key)
    if result is None:
        raise HTTPException(404, "Case not found")
    return result


async def _then_detail(work: Awaitable[Any], graph: Graph, pg: Pg, key: str) -> CaseDetail:
    """Run a change, then return the case as it now stands."""
    try:
        await work
    except LookupError as exc:
        raise HTTPException(404, "Case not found") from exc
    except cases.CaseError as exc:
        raise HTTPException(409, str(exc)) from exc
    return await _detail(graph, pg, key)


@router.get("", response_model=list[CaseSummary])
async def list_cases(graph: Graph, pg: Pg, _: Reader) -> list[CaseSummary]:
    """The case queue: every network of people, claims and providers, highest score first."""
    return await cases.list_cases(graph, pg)


@router.get("/agent/status", response_model=AgentStatus)
async def agent_status(_: Reader) -> AgentStatus:
    """Whether agent mode is switched on (it needs an Anthropic API key)."""
    return AgentStatus(enabled=agent.enabled(), model=get_settings().agent_model)


@router.get("/{case_key}", response_model=CaseDetail)
async def get_case(case_key: str, graph: Graph, pg: Pg, _: Reader) -> CaseDetail:
    return await _detail(graph, pg, case_key)


@router.get("/{case_key}/claims", response_model=CaseClaims)
async def case_claims(case_key: str, graph: Graph, _: Reader) -> CaseClaims:
    """The claims in the case with their details and who is on each, newest loss first (up to
    1,000)."""
    result = await cases.case_claims(graph, case_key)
    if result is None:
        raise HTTPException(404, "Case not found")
    return result


@router.patch("/{case_key}", response_model=CaseDetail)
async def update_case(case_key: str, body: CaseUpdate, graph: Graph, pg: Pg,
                      user: Investigator) -> CaseDetail:
    return await _then_detail(cases.update_case(graph, pg, user, case_key, body),
                              graph, pg, case_key)


@router.post("/{case_key}/notes", response_model=CaseDetail, status_code=201)
async def add_note(case_key: str, body: NoteIn, graph: Graph, pg: Pg,
                   user: Investigator) -> CaseDetail:
    """A diary entry (HTML). Notes can be changed until the case is closed."""
    return await _then_detail(cases.add_note(graph, pg, user, case_key, body),
                              graph, pg, case_key)


@router.patch("/{case_key}/notes/{note_id}", response_model=CaseDetail)
async def update_note(case_key: str, note_id: uuid.UUID, body: NoteUpdate, graph: Graph, pg: Pg,
                      user: Investigator) -> CaseDetail:
    return await _then_detail(cases.update_note(graph, pg, user, case_key, note_id, body),
                              graph, pg, case_key)


@router.delete("/{case_key}/notes/{note_id}", response_model=CaseDetail)
async def delete_note(case_key: str, note_id: uuid.UUID, graph: Graph, pg: Pg,
                      user: Investigator) -> CaseDetail:
    return await _then_detail(cases.delete_note(graph, pg, user, case_key, note_id),
                              graph, pg, case_key)


@router.post("/{case_key}/tasks", response_model=CaseDetail, status_code=201)
async def add_task(case_key: str, body: TaskIn, graph: Graph, pg: Pg,
                   user: Investigator) -> CaseDetail:
    return await _then_detail(cases.add_task(graph, pg, user, case_key, body),
                              graph, pg, case_key)


@router.patch("/{case_key}/tasks/{task_id}", response_model=CaseDetail)
async def update_task(case_key: str, task_id: uuid.UUID, body: TaskUpdate, graph: Graph, pg: Pg,
                      user: Investigator) -> CaseDetail:
    return await _then_detail(cases.update_task(graph, pg, user, case_key, task_id, body),
                              graph, pg, case_key)


@router.delete("/{case_key}/tasks/{task_id}", response_model=CaseDetail)
async def delete_task(case_key: str, task_id: uuid.UUID, graph: Graph, pg: Pg,
                      user: Investigator) -> CaseDetail:
    return await _then_detail(cases.delete_task(graph, pg, user, case_key, task_id),
                              graph, pg, case_key)


@router.post("/{case_key}/documents", response_model=CaseDetail, status_code=201)
async def add_document(case_key: str, graph: Graph, pg: Pg, user: Investigator,
                       file: UploadFile = File(), note: str | None = Form(None),
                       task_id: uuid.UUID | None = Form(None)) -> CaseDetail:
    data = await file.read(cases.MAX_DOCUMENT_BYTES + 1)
    return await _then_detail(
        cases.add_document(graph, pg, user, case_key, file.filename or "document",
                           file.content_type or "application/octet-stream", data, note, task_id),
        graph, pg, case_key)


@router.patch("/{case_key}/documents/{document_id}", response_model=CaseDetail)
async def tag_document(case_key: str, document_id: uuid.UUID, body: DocumentTag, graph: Graph,
                       pg: Pg, user: Investigator) -> CaseDetail:
    """Tag a document to a task, or clear the tag."""
    return await _then_detail(
        cases.tag_document(graph, pg, user, case_key, document_id, body.task_id),
        graph, pg, case_key)


@router.get("/{case_key}/documents/{document_id}")
async def download_document(case_key: str, document_id: uuid.UUID, pg: Pg,
                            _: Reader) -> Response:
    doc = await cases.get_document(pg, case_key, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    # Always a download, never rendered in the app's origin, whatever the file claims to be.
    return StreamingResponse(iter([doc.data]), media_type="application/octet-stream", headers={
        "content-disposition": f"attachment; filename*=UTF-8''{quote(doc.filename, safe='')}",
        "x-content-type-options": "nosniff",
        "content-length": str(doc.size),
    })


@router.delete("/{case_key}/documents/{document_id}", response_model=CaseDetail)
async def delete_document(case_key: str, document_id: uuid.UUID, graph: Graph, pg: Pg,
                          user: Investigator) -> CaseDetail:
    return await _then_detail(cases.delete_document(graph, pg, user, case_key, document_id),
                              graph, pg, case_key)


@router.put("/{case_key}/report", response_model=CaseDetail)
async def save_report(case_key: str, body: Report, graph: Graph, pg: Pg,
                      user: Investigator) -> CaseDetail:
    return await _then_detail(cases.save_report(graph, pg, user, case_key, body),
                              graph, pg, case_key)


@router.post("/{case_key}/report/draft", response_model=ReportDraft)
async def draft_report(case_key: str, graph: Graph, pg: Pg, user: Investigator) -> ReportDraft:
    """The agent reads the case's notes and documents and proposes a closing report. It saves
    nothing; what it was shown is sent to the Claude API."""
    try:
        return await cases.draft_report(graph, pg, user, case_key)
    except LookupError as exc:
        raise HTTPException(404, "Case not found") from exc
    except cases.CaseError as exc:
        raise HTTPException(409, str(exc)) from exc
    except agent.AgentError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/{case_key}/close", response_model=CaseDetail)
async def close_case(case_key: str, body: CaseClose, graph: Graph, pg: Pg,
                     user: Investigator) -> CaseDetail:
    return await _then_detail(cases.close_case(graph, pg, user, case_key, body),
                              graph, pg, case_key)
