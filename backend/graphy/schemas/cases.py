import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from graphy.schemas.graph import Network

CaseStatus = Literal["new", "investigating", "confirmed", "insufficient", "dismissed"]
# How a case ends: fraud confirmed, not enough information to say, or dismissed.
Outcome = Literal["confirmed", "insufficient", "dismissed"]
EventKind = Literal["note", "status", "assignee", "task", "document", "report"]
TaskStatus = Literal["pending", "received", "not_received"]


class CaseSummary(BaseModel):
    """One row of the case queue: the network's facts plus where the case stands."""

    case_key: str
    status: CaseStatus
    assignee: str | None
    updated_at: datetime | None  # None until someone has acted on it
    focus_id: str
    focus_label: str
    size: int  # entities in the network
    links: int
    types: dict[str, int]  # members per entity type, e.g. {"Person": 7, "Claim": 5}
    aliases: int  # probable-alias links inside the network
    via: list[str]
    claim_count: int
    claimed_amount: float  # what its claims add up to
    score: int
    severity: Literal["low", "medium", "high"]
    flags: list[str]
    open_tasks: int = 0


class CaseMember(BaseModel):
    """An entity in the case: a person, company, claim, policy, vehicle or provider."""

    entity_id: str
    label: str
    entity_type: str
    claims: int  # claims it is tied to
    roles: list[str]  # what it is on those claims: insured, driver, represents...


class ClaimParty(BaseModel):
    entity_id: str
    label: str
    entity_type: str
    role: str


class CaseClaim(BaseModel):
    """A claim in the case, with what is on file for it and who is on it."""

    entity_id: str
    claim: str  # the claim number
    loss_date: str | None
    fnol_date: str | None  # first notice of loss
    loss_types: list[str]
    description: str | None
    status: str | None
    amount: float | None
    siu_referred: bool
    siu_accepted: bool
    siu_outcome: str | None
    parties: list[ClaimParty]


class CaseClaims(BaseModel):
    total: int
    items: list[CaseClaim]  # newest loss first, up to the limit


class CaseEventOut(BaseModel):
    id: str
    kind: EventKind
    body: str
    author: str
    created_at: datetime


class TaskOut(BaseModel):
    id: str
    title: str
    assignee: str | None
    due_date: date | None
    status: TaskStatus
    done: bool  # closed
    done_at: datetime | None
    created_by: str
    created_at: datetime


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    note: str | None
    task_id: str | None  # the task it is tagged to
    uploaded_by: str
    created_at: datetime


class NoteOut(BaseModel):
    id: str
    title: str
    body: str  # sanitized HTML
    preview: str  # the first words, as plain text
    task_id: str | None
    created_by: str
    created_at: datetime
    updated_by: str | None
    updated_at: datetime | None  # None until edited


class Authority(BaseModel):
    """Whether the case was reported to an authority (a fraud bureau, the insurance department,
    law enforcement), to whom, and the notes that go with it."""

    reported: bool = False
    name: str = Field(default="", max_length=255)
    reference: str = Field(default="", max_length=255)
    reported_on: date | None = None
    notes: str = Field(default="", max_length=4000)


class Report(BaseModel):
    """The closing report. `outcome` is open until the case is closed."""

    outcome: Outcome | None = None
    summary: str = Field(default="", max_length=8000)
    recommendation: str = Field(default="", max_length=4000)
    amount_recovered: float | None = Field(default=None, ge=0)
    authority: Authority = Authority()


class CaseDetail(BaseModel):
    summary: CaseSummary
    network: Network  # the live indicators, with the rule behind each
    members: list[CaseMember]
    events: list[CaseEventOut]
    tasks: list[TaskOut]
    documents: list[DocumentOut]
    notes: list[NoteOut]
    report: Report | None
    closed_at: datetime | None
    closed_by: str | None


class CaseUpdate(BaseModel):
    """Only the fields sent are changed; `assignee: null` unassigns. Closing goes through
    CaseClose, so `status` here is only new or investigating (which reopens)."""

    status: CaseStatus | None = None
    assignee: str | None = Field(default=None, max_length=255)


class NoteIn(BaseModel):
    title: str = Field(default="", max_length=255)
    body: str = Field(default="", max_length=200_000)  # HTML from the editor
    task_id: uuid.UUID | None = None


class NoteUpdate(BaseModel):
    """Only the fields sent are changed; `task_id: null` removes the tag."""

    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=200_000)
    task_id: uuid.UUID | None = None


class DocumentTag(BaseModel):
    task_id: uuid.UUID | None = None  # null removes the tag


class AgentStatus(BaseModel):
    enabled: bool
    model: str


class UnreadDocument(BaseModel):
    filename: str
    reason: str


class ReportDraft(BaseModel):
    """What the agent proposes for the closing report. Nothing is saved: a person reads it,
    changes it and saves or closes."""

    outcome: Outcome | None  # None when the material does not settle it
    summary: str
    recommendation: str
    amount_recovered: float | None
    caveats: list[str]
    used_documents: list[str]
    used_notes: int
    unread: list[UnreadDocument]
    model: str


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    assignee: str | None = Field(default=None, max_length=255)
    due_date: date | None = None


class TaskUpdate(BaseModel):
    """Only the fields sent are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    assignee: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    status: TaskStatus | None = None
    done: bool | None = None  # close or reopen the task


class CaseClose(BaseModel):
    outcome: Outcome
    summary: str = Field(min_length=1, max_length=8000)
    recommendation: str = Field(default="", max_length=4000)
    amount_recovered: float | None = Field(default=None, ge=0)
    authority: Authority = Authority()
