import io
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from graphy.schemas.cases import (
    CaseClaim,
    CaseClaims,
    CaseDetail,
    CaseMember,
    CaseSummary,
    ClaimParty,
    TaskOut,
)
from graphy.schemas.graph import Hit, HitMatch, Network
from graphy.services import agent
from graphy.services.agent import AgentError, Draft, gather

NOW = datetime(2026, 10, 1, tzinfo=UTC)
TASK = "11111111-1111-1111-1111-111111111111"


def detail() -> CaseDetail:
    hit = Hit(rule_id="medical-and-legal-on-three-claims", title="Same clinic and attorney",
              severity="high", points=25, detail="Acme Clinic and Smith Law are together on 2 claims",
              entities=["clinic", "law", "c1", "c2"],
              condition="Fires when a medical provider and an attorney are together on at least 2 claims",
              matches=[HitMatch(kind="claims", entities=["clinic", "law"], claims=["c1", "c2"])])
    net = Network(network_id="c1", size=5, links=4, types={"Person": 1, "Claim": 2, "MedicalProvider": 1,
                                                           "LegalRep": 1}, aliases=0, focus_id="clinic",
                  focus_label="Acme Clinic", via=["treated_for"], score=80, severity="high",
                  flags=[], hits=[hit], members=["c1", "c2", "clinic", "law", "x"])
    summary = CaseSummary(case_key="c1", status="investigating", assignee="j@x.example",
                          updated_at=None, focus_id="clinic", focus_label="Acme Clinic", size=5,
                          links=4, types=net.types, aliases=0, via=["treated_for"], claim_count=2,
                          claimed_amount=9000.0, score=80, severity="high", flags=[], open_tasks=1)
    task = TaskOut(id=TASK, title="Request medical records", assignee=None, due_date=None,
                   status="not_received", done=False, done_at=None, created_by="j", created_at=NOW)
    return CaseDetail(
        summary=summary, network=net,
        members=[CaseMember(entity_id="x", label="Jane Roe", entity_type="Person", claims=2,
                            roles=["claimant"]),
                 CaseMember(entity_id="clinic", label="Acme Clinic", entity_type="MedicalProvider",
                            claims=2, roles=["treated_for"]),
                 CaseMember(entity_id="law", label="Smith Law", entity_type="LegalRep", claims=2,
                            roles=["represents"]),
                 CaseMember(entity_id="c1", label="CLM-1", entity_type="Claim", claims=0, roles=[]),
                 CaseMember(entity_id="c2", label="CLM-2", entity_type="Claim", claims=0, roles=[])],
        events=[], tasks=[task], documents=[], notes=[], report=None, closed_at=None,
        closed_by=None)


CLAIMS = CaseClaims(total=2, items=[
    CaseClaim(entity_id="c1", claim="CLM-1", loss_date="2026-03-02", fnol_date="2026-03-04",
              loss_types=["Bodily Injury"], description="Rear-end collision", status="Under review",
              amount=6000.0, siu_referred=True, siu_accepted=False, siu_outcome=None,
              parties=[ClaimParty(entity_id="x", label="Jane Roe", entity_type="Person",
                                  role="claimant")]),
    CaseClaim(entity_id="c2", claim="CLM-2", loss_date="2026-04-10", fnol_date=None, loss_types=[],
              description=None, status=None, amount=3000.0, siu_referred=False,
              siu_accepted=False, siu_outcome=None, parties=[])])


def doc(name: str, data: bytes, ctype: str = "", task_id: str | None = None, note: str | None = None):
    return SimpleNamespace(filename=name, content_type=ctype, data=data, size=len(data),
                           note=note, task_id=task_id)


def note(title: str, body: str, task_id: str | None = None):
    return SimpleNamespace(title=title, body=body, created_at=NOW, created_by="j@x.example",
                           task_id=task_id)


def docx(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml",
                   f"<w:document><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:document>")
    return buf.getvalue()


def test_the_agent_is_shown_the_case_facts_notes_and_readable_documents() -> None:
    m = gather(detail(), CLAIMS, [
        doc("statement.txt", b"Claimant says she was not in the car", "text/plain", TASK, "recorded"),
        doc("letter.docx", docx("We deny everything")),
        doc("scan.pdf", b"%PDF-1.4 x", "application/pdf"),
        doc("photo.png", b"\x89PNG", ""),
        doc("sheet.xlsx", b"PK", ""),
    ], [note("Call", "<p>The clinic confirmed <b>one</b> referrer</p>", TASK)])
    text = "\n".join(m.sections)
    assert "Jane Roe: Person (claimant), on 2 claims" in text
    assert "CLM-1: lost 2026-03-02, filed 2026-03-04, Bodily Injury, $6,000.00, Under review, referred to SIU" in text
    assert "Matched claims: Acme Clinic, Smith Law on CLM-1, CLM-2" in text
    assert "Request medical records [not received]" in text
    assert "The clinic confirmed one referrer" in text and "about task: Request medical records" in text
    assert "Claimant says she was not in the car" in text and "We deny everything" in text
    assert [b["type"] for b in m.blocks if b["type"] != "text"] == ["document", "image"]
    assert m.used_documents == ["statement.txt", "letter.docx", "scan.pdf", "photo.png"]
    assert [(u.filename, u.reason) for u in m.unread] == [("sheet.xlsx", ".xlsx files cannot be read yet")]


def test_titles_and_names_cannot_break_out_of_their_tags() -> None:
    m = gather(detail(), None, [doc('a"><x>.txt', b"hi", "text/plain")],
               [note('t"><injected>', "<p>body</p>")])
    text = "\n".join(m.sections)
    assert "<injected>" not in text and "<x>" not in text


def test_long_documents_are_cut_and_the_draft_says_so() -> None:
    big = doc("big.txt", b"x" * (agent.MAX_DOCUMENT_CHARS + 5), "text/plain")
    m = gather(detail(), None, [big], [])
    assert m.truncated == ["document “big.txt”"]
    assert "x" * agent.MAX_DOCUMENT_CHARS in "\n".join(m.sections)


class FakeClient:
    def __init__(self, result=None, stop_reason: str = "end_turn") -> None:
        self.calls: list[dict] = []
        self.result, self.stop_reason = result, stop_reason
        self.messages = self

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self.result, stop_reason=self.stop_reason)


async def test_a_draft_comes_back_for_review_with_what_could_not_be_read() -> None:
    client = FakeClient(Draft(outcome="insufficient", summary="S [doc: statement.txt]",
                              recommendation="", amount_recovered=None, caveats=["No records"]))
    out = await agent.draft(detail(), CLAIMS, [doc("statement.txt", b"x", "text/plain"),
                                               doc("s.xlsx", b"PK")],
                            [note("Call", "<p>x</p>")], client=client)
    assert out.outcome == "insufficient" and out.summary.startswith("S")
    assert out.used_documents == ["statement.txt"] and out.used_notes == 1
    assert out.caveats[0] == "No records" and any("s.xlsx" in c for c in out.caveats)
    (call,) = client.calls
    assert call["system"] == agent.SYSTEM and call["output_format"] is agent.Draft
    assert call["messages"][0]["content"][-1]["type"] == "text"


async def test_a_confirmed_draft_keeps_its_outcome_and_amount() -> None:
    client = FakeClient(Draft(outcome="confirmed", summary="S", recommendation="R",
                              amount_recovered=1500.0, caveats=[]))
    out = await agent.draft(detail(), None, [], [], client=client)
    assert (out.outcome, out.amount_recovered, out.recommendation) == ("confirmed", 1500.0, "R")


async def test_a_refusal_or_an_unreadable_reply_is_an_error() -> None:
    with pytest.raises(AgentError, match="declined"):
        await agent.draft(detail(), None, [], [], client=FakeClient(None, "refusal"))
    with pytest.raises(AgentError, match="could not be read"):
        await agent.draft(detail(), None, [], [], client=FakeClient(None))


async def test_agent_mode_is_off_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(agent, "get_settings",
                        lambda: SimpleNamespace(anthropic_api_key=None, agent_model="m"))
    assert not agent.enabled()
    with pytest.raises(AgentError) as err:
        await agent.draft(detail(), None, [], [])
    assert err.value.status == 503
