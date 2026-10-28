"""Case management over the scored networks.

Every network of three or more entities (people, companies, claims, policies, vehicles,
providers) is a case. Its facts and indicators are computed live from the graph; what people do
about it (status, owner, notes, tasks, documents and the closing report) lives in PostgreSQL and
is written the first time someone acts. A case is identified by its lowest entity id.
"""

import uuid
from datetime import UTC, datetime

from neo4j import AsyncSession as GraphSession
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from graphy.auth import User
from graphy.db.models import CaseDocument, CaseEvent, CaseNote, CaseTask, FraudCase
from graphy.schemas.cases import (
    CaseClaim,
    CaseClaims,
    CaseClose,
    CaseDetail,
    CaseEventOut,
    CaseMember,
    CaseSummary,
    CaseUpdate,
    DocumentOut,
    NoteIn,
    NoteOut,
    NoteUpdate,
    Report,
    ReportDraft,
    TaskIn,
    TaskOut,
    TaskUpdate,
)
from graphy.schemas.graph import Network
from graphy.services import agent, audit, graph_queries, notes
from graphy.services.analytics_rules import published_rules

MIN_NETWORK = 3
MAX_CASES = 1_000
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

STATUS_LABEL = {"new": "New", "investigating": "Investigating", "confirmed": "Confirmed fraud",
                "insufficient": "Not enough information", "dismissed": "Dismissed"}
CLOSED = ("confirmed", "insufficient", "dismissed")
TASK_STATUS = {"pending": "pending", "received": "received", "not_received": "not received"}


class CaseError(Exception):
    """A request the case's current state does not allow."""


def case_key(n: Network) -> str:
    return min(n.members)


def _summary(n: Network, row: FraudCase | None, amounts: dict[str, float],
             open_tasks: int = 0) -> CaseSummary:
    return CaseSummary(
        case_key=case_key(n), status=row.status if row else "new",  # type: ignore[arg-type]
        assignee=row.assignee if row else None, updated_at=row.updated_at if row else None,
        focus_id=n.focus_id, focus_label=n.focus_label, size=n.size, links=n.links,
        types=n.types, aliases=n.aliases, via=n.via, claim_count=n.types.get("Claim", 0),
        claimed_amount=sum(amounts.get(m, 0.0) for m in n.members), score=n.score,
        severity=n.severity, flags=n.flags, open_tasks=open_tasks,
    )


async def list_cases(graph: GraphSession, pg: AsyncSession) -> list[CaseSummary]:
    """The queue: every network, highest score first, with where its case stands."""
    nets = await graph_queries.networks(graph, MIN_NETWORK, MAX_CASES, await published_rules(pg),
                                        with_members=True)
    amounts = await graph_queries.claim_amounts(graph)
    rows = {c.case_key: c for c in await pg.scalars(select(FraudCase))}
    open_tasks = {r[0]: r[1] for r in await pg.execute(
        select(CaseTask.case_id, func.count()).where(CaseTask.done.is_(False))
        .group_by(CaseTask.case_id))}
    return [_summary(n, rows.get(case_key(n)), amounts,
                     open_tasks.get(rows[case_key(n)].id, 0) if case_key(n) in rows else 0)
            for n in nets]


async def _row(pg: AsyncSession, key: str) -> FraudCase | None:
    return await pg.scalar(select(FraudCase).where(FraudCase.case_key == key))


async def _all(pg: AsyncSession, model: type, row: FraudCase | None, *order: object) -> list:
    if row is None:
        return []
    return list(await pg.scalars(select(model).where(model.case_id == row.id).order_by(*order)))


async def get_case(graph: GraphSession, pg: AsyncSession, key: str) -> CaseDetail | None:
    """None when no entity with that id is on the graph. A key that has since been absorbed
    into a network with a lower id resolves to that network's case."""
    net = await graph_queries.entity_network(graph, key, await published_rules(pg))
    if net is None:
        return None
    row = await _row(pg, case_key(net))
    events = await _all(pg, CaseEvent, row, CaseEvent.created_at)
    tasks = await _all(pg, CaseTask, row, CaseTask.done, CaseTask.due_date, CaseTask.created_at)
    documents = await _all(pg, CaseDocument, row, CaseDocument.created_at)
    note_rows = await _all(pg, CaseNote, row, CaseNote.created_at)
    return CaseDetail(
        summary=_summary(net, row, await graph_queries.claim_amounts(graph),
                         sum(not t.done for t in tasks)),
        network=net,
        members=[CaseMember(**m) for m in await graph_queries.members_of(graph, net.members)],
        events=[CaseEventOut(id=str(e.id), kind=e.kind, body=e.body,  # type: ignore[arg-type]
                             author=e.author, created_at=e.created_at) for e in events],
        tasks=[TaskOut(id=str(t.id), title=t.title, assignee=t.assignee, due_date=t.due_date,
                       status=t.status, done=t.done, done_at=t.done_at, created_by=t.created_by,
                       created_at=t.created_at) for t in tasks],
        documents=[DocumentOut(id=str(d.id), filename=d.filename, content_type=d.content_type,
                               size=d.size, note=d.note, uploaded_by=d.uploaded_by,
                               task_id=str(d.task_id) if d.task_id else None,
                               created_at=d.created_at) for d in documents],
        notes=[NoteOut(id=str(n.id), title=n.title, body=n.body, preview=notes.preview_of(n.body),
                       task_id=str(n.task_id) if n.task_id else None, created_by=n.created_by,
                       created_at=n.created_at, updated_by=n.updated_by,
                       updated_at=n.updated_at) for n in note_rows],
        report=Report.model_validate(row.report) if row and row.report else None,
        closed_at=row.closed_at if row else None, closed_by=row.closed_by if row else None,
    )


async def case_claims(graph: GraphSession, key: str, limit: int = 1_000) -> CaseClaims | None:
    """Every claim in the case with what is on file for it and who is on it."""
    net = await graph_queries.entity_network(graph, key)
    if net is None:
        return None
    total, rows = await graph_queries.claims_of(graph, net.members, limit)
    return CaseClaims(total=total, items=[CaseClaim(**r) for r in rows])


async def _ensure(graph: GraphSession, pg: AsyncSession, key: str) -> tuple[FraudCase, str] | None:
    net = await graph_queries.entity_network(graph, key)
    if net is None:
        return None
    key = case_key(net)
    row = await _row(pg, key)
    if row is None:
        row = FraudCase(case_key=key, status="new")
        pg.add(row)
        await pg.flush()
    return row, key


def _event(pg: AsyncSession, row: FraudCase, user: User, kind: str, body: str) -> None:
    pg.add(CaseEvent(case_id=row.id, kind=kind, author=user.subject, body=body))
    row.updated_at = datetime.now(UTC)


async def _act(graph: GraphSession, pg: AsyncSession, key: str) -> tuple[FraudCase, str]:
    found = await _ensure(graph, pg, key)
    if found is None:
        raise LookupError(key)
    return found


async def update_case(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                      body: CaseUpdate) -> None:
    row, key = await _act(graph, pg, key)
    before = {"status": row.status, "assignee": row.assignee}
    if body.status in CLOSED:
        raise CaseError("Close a case with its closing report")
    if body.status is not None and body.status != row.status:
        reopened = row.status in CLOSED
        _event(pg, row, user, "status",
               f"Case reopened as {STATUS_LABEL[body.status]}" if reopened else
               f"Status changed from {STATUS_LABEL[row.status]} to {STATUS_LABEL[body.status]}")
        row.status = body.status
        if reopened:
            row.closed_at = row.closed_by = None
    if "assignee" in body.model_fields_set and body.assignee != row.assignee:
        _event(pg, row, user, "assignee",
               f"Assigned to {body.assignee}" if body.assignee else "Unassigned")
        row.assignee = body.assignee
    after = {"status": row.status, "assignee": row.assignee}
    if after != before:
        await audit.record(pg, user, "case.update", "fraud_case", key, before=before, after=after)
    await pg.commit()


def _editable(row: FraudCase) -> None:
    if row.status in CLOSED:
        raise CaseError("The case is closed; reopen it to change its notes")


async def _tag(pg: AsyncSession, row: FraudCase, task_id: uuid.UUID | None) -> uuid.UUID | None:
    """A task of this case, or None; a task of another case is not found."""
    if task_id is None:
        return None
    return (await _owned(pg, CaseTask, row, task_id)).id


async def add_note(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                   body: NoteIn) -> None:
    row, key = await _act(graph, pg, key)
    _editable(row)
    html = notes.clean(body.body)
    if not body.title.strip() and not notes.text_of(html):
        raise CaseError("A note needs a title or some text")
    pg.add(CaseNote(case_id=row.id, title=notes.title_of(body.title, html), body=html,
                    task_id=await _tag(pg, row, body.task_id), created_by=user.subject))
    _event(pg, row, user, "note", f"Note added: {notes.title_of(body.title, html)}")
    await audit.record(pg, user, "case.note.add", "fraud_case", key)
    await pg.commit()


async def update_note(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                      note_id: uuid.UUID, body: NoteUpdate) -> None:
    row, key = await _act(graph, pg, key)
    _editable(row)
    note: CaseNote = await _owned(pg, CaseNote, row, note_id)
    sent = body.model_fields_set
    if body.body is not None:
        note.body = notes.clean(body.body)
    if body.title is not None or body.body is not None:
        note.title = notes.title_of(body.title if body.title is not None else note.title,
                                    note.body)
    if "task_id" in sent:
        note.task_id = await _tag(pg, row, body.task_id)
    note.updated_by, note.updated_at = user.subject, datetime.now(UTC)
    _event(pg, row, user, "note", f"Note edited: {note.title}")
    await audit.record(pg, user, "case.note.update", "fraud_case", key)
    await pg.commit()


async def delete_note(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                      note_id: uuid.UUID) -> None:
    row, key = await _act(graph, pg, key)
    _editable(row)
    note: CaseNote = await _owned(pg, CaseNote, row, note_id)
    _event(pg, row, user, "note", f"Note deleted: {note.title}")
    await pg.delete(note)
    await audit.record(pg, user, "case.note.delete", "fraud_case", key)
    await pg.commit()


async def add_task(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                   body: TaskIn) -> None:
    row, key = await _act(graph, pg, key)
    pg.add(CaseTask(case_id=row.id, title=body.title, assignee=body.assignee,
                    due_date=body.due_date, created_by=user.subject))
    _event(pg, row, user, "task", f"Task added: {body.title}")
    await audit.record(pg, user, "case.task.add", "fraud_case", key)
    await pg.commit()


async def _owned(pg: AsyncSession, model: type, row: FraudCase, item_id: uuid.UUID):  # noqa: ANN202
    item = await pg.scalar(select(model).where(model.id == item_id, model.case_id == row.id))
    if item is None:
        raise LookupError(str(item_id))
    return item


async def update_task(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                      task_id: uuid.UUID, body: TaskUpdate) -> None:
    row, key = await _act(graph, pg, key)
    task: CaseTask = await _owned(pg, CaseTask, row, task_id)
    sent = body.model_fields_set
    if body.title is not None:
        task.title = body.title
    if "assignee" in sent:
        task.assignee = body.assignee
    if "due_date" in sent:
        task.due_date = body.due_date
    if body.status is not None and body.status != task.status:
        task.status = body.status
        _event(pg, row, user, "task", f"Task marked {TASK_STATUS[body.status]}: {task.title}")
    if body.done is not None and body.done != task.done:
        task.done = body.done
        task.done_at = datetime.now(UTC) if body.done else None
        _event(pg, row, user, "task", f"Task {'closed' if body.done else 'reopened'}: {task.title}")
    if sent & {"title", "assignee", "due_date"}:
        _event(pg, row, user, "task", f"Task edited: {task.title}")
    await audit.record(pg, user, "case.task.update", "fraud_case", key)
    await pg.commit()


async def delete_task(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                      task_id: uuid.UUID) -> None:
    row, key = await _act(graph, pg, key)
    task: CaseTask = await _owned(pg, CaseTask, row, task_id)
    _event(pg, row, user, "task", f"Task removed: {task.title}")
    await pg.delete(task)
    await audit.record(pg, user, "case.task.delete", "fraud_case", key)
    await pg.commit()


async def add_document(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                       filename: str, content_type: str, data: bytes, note: str | None,
                       task_id: uuid.UUID | None = None) -> None:
    if len(data) > MAX_DOCUMENT_BYTES:
        raise CaseError(f"Files can be up to {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB")
    row, key = await _act(graph, pg, key)
    pg.add(CaseDocument(case_id=row.id, filename=filename[:255], content_type=content_type[:128],
                        size=len(data), note=note or None, data=data, uploaded_by=user.subject,
                        task_id=await _tag(pg, row, task_id)))
    _event(pg, row, user, "document", f"Document uploaded: {filename[:255]}")
    await audit.record(pg, user, "case.document.add", "fraud_case", key)
    await pg.commit()


async def tag_document(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                       document_id: uuid.UUID, task_id: uuid.UUID | None) -> None:
    row, key = await _act(graph, pg, key)
    doc: CaseDocument = await _owned(pg, CaseDocument, row, document_id)
    doc.task_id = await _tag(pg, row, task_id)
    _event(pg, row, user, "document", f"Document {'tagged to a task' if task_id else 'untagged'}: "
                                      f"{doc.filename}")
    await audit.record(pg, user, "case.document.tag", "fraud_case", key)
    await pg.commit()


async def get_document(pg: AsyncSession, key: str, document_id: uuid.UUID) -> CaseDocument | None:
    """Takes the key as listed; a case that has since merged into another is not followed."""
    row = await _row(pg, key)
    if row is None:
        return None
    return await pg.scalar(select(CaseDocument).where(
        CaseDocument.id == document_id, CaseDocument.case_id == row.id)
        .options(undefer(CaseDocument.data)))


async def delete_document(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                          document_id: uuid.UUID) -> None:
    row, key = await _act(graph, pg, key)
    doc: CaseDocument = await _owned(pg, CaseDocument, row, document_id)
    _event(pg, row, user, "document", f"Document removed: {doc.filename}")
    await pg.delete(doc)
    await audit.record(pg, user, "case.document.delete", "fraud_case", key)
    await pg.commit()


async def save_report(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                      body: Report) -> None:
    """Keep a draft of the closing report; the case stays open."""
    row, key = await _act(graph, pg, key)
    if row.status in CLOSED:
        raise CaseError("The case is closed; reopen it to change the report")
    row.report = body.model_dump(mode="json")
    row.updated_at = datetime.now(UTC)
    await pg.commit()


async def draft_report(graph: GraphSession, pg: AsyncSession, user: User,
                       key: str) -> ReportDraft:
    """Ask the agent for a draft closing report from the case's notes and documents. Nothing is
    saved."""
    if not agent.enabled():
        raise agent.AgentError("Agent mode is off: set an Anthropic API key "
                               "(GRAPHY_ANTHROPIC_API_KEY)", 503)
    detail = await get_case(graph, pg, key)
    if detail is None:
        raise LookupError(key)
    if detail.summary.status in CLOSED:
        raise CaseError("The case is closed; reopen it to draft a new report")
    row = await _row(pg, detail.summary.case_key)
    docs: list[CaseDocument] = []
    note_rows: list[CaseNote] = []
    if row is not None:
        docs = list(await pg.scalars(
            select(CaseDocument).where(CaseDocument.case_id == row.id)
            .options(undefer(CaseDocument.data)).order_by(CaseDocument.created_at)))
        note_rows = list(await pg.scalars(select(CaseNote).where(CaseNote.case_id == row.id)))
    result = await agent.draft(detail, await case_claims(graph, key), docs, note_rows)
    await audit.record(pg, user, "case.agent.draft", "fraud_case", detail.summary.case_key,
                       after={"documents": len(result.used_documents), "notes": len(note_rows),
                              "model": result.model})
    await pg.commit()
    return result


async def close_case(graph: GraphSession, pg: AsyncSession, user: User, key: str,
                     body: CaseClose) -> None:
    row, key = await _act(graph, pg, key)
    if row.status in CLOSED:
        raise CaseError("The case is already closed")
    row.report = Report.model_validate(body.model_dump()).model_dump(mode="json")
    row.status, row.closed_at, row.closed_by = body.outcome, datetime.now(UTC), user.subject
    told = body.authority.name or "an authority"
    reported_to = body.authority.name if body.authority.reported else None
    _event(pg, row, user, "report", f"Case closed: {STATUS_LABEL[body.outcome]}"
           + (f"; reported to {told}" if body.authority.reported else ""))
    await audit.record(pg, user, "case.close", "fraud_case", key,
                       after={"outcome": body.outcome, "amount_recovered": body.amount_recovered,
                              "reported_to": reported_to})
    await pg.commit()
