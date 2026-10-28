"""API tests that need no databases. Integration tests against real Neo4j and PostgreSQL
(TRD 11) run in CI with service containers."""

import pytest
from fastapi.testclient import TestClient

from graphy.auth import Role, User, current_user
from graphy.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def as_user(*roles: Role) -> None:
    app.dependency_overrides[current_user] = lambda: User("t@example.com", frozenset(roles))


@pytest.fixture(autouse=True)
def _reset() -> None:
    yield
    app.dependency_overrides.clear()


def test_live(client: TestClient) -> None:
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.headers["x-request-id"]


def test_request_id_is_echoed(client: TestClient) -> None:
    r = client.get("/api/v1/health/live", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def test_audit_requires_compliance(client: TestClient) -> None:
    as_user(Role.ANALYST, Role.ADMIN)
    assert client.get("/api/v1/audit/events").status_code == 403


def test_read_only_cannot_create_rule_sets(client: TestClient) -> None:
    as_user(Role.READ_ONLY)
    r = client.post("/api/v1/resolution/rule-sets",
                    json={"name": "p1", "entity_type": "Person", "document": {}})
    assert r.status_code == 403


def test_planned_endpoints_say_so(client: TestClient) -> None:
    as_user(Role.DETECTION_ANALYST)
    r = client.post("/api/v1/analytics/runs")
    assert r.status_code == 501
    assert "not implemented yet" in r.json()["detail"]


def test_openapi_lists_contract(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    for p in ("/api/v1/graph/neighborhood", "/api/v1/entities/{entity_id}/attributes",
              "/api/v1/resolution/rule-sets/{rule_set_id}/publish", "/api/v1/search",
              "/api/v1/audit/events", "/api/v1/ingestion/batches"):
        assert p in paths


def test_me_reports_roles(client: TestClient) -> None:
    as_user(Role.STEWARD, Role.ANALYST)
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    assert r.json() == {"subject": "t@example.com", "roles": ["analyst", "steward"]}


@pytest.mark.parametrize(("method", "path"), [
    ("post", "/api/v1/analytics/rules/preview"),
    ("post", "/api/v1/analytics/rules/00000000-0000-0000-0000-000000000000/publish"),
    ("post", "/api/v1/analytics/rules/00000000-0000-0000-0000-000000000000/retire"),
    ("delete", "/api/v1/analytics/rules/00000000-0000-0000-0000-000000000000"),
])
def test_read_only_cannot_change_the_rule_library(client: TestClient, method: str,
                                                  path: str) -> None:
    as_user(Role.READ_ONLY)
    kwargs = {"json": {}} if method == "post" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 403


def test_read_only_cannot_work_a_case(client: TestClient) -> None:
    as_user(Role.READ_ONLY)
    assert client.patch("/api/v1/cases/e1", json={"status": "investigating"}).status_code == 403
    assert client.post("/api/v1/cases/e1/notes", json={"body": "<p>x</p>"}).status_code == 403


def test_a_note_body_is_bounded(client: TestClient) -> None:
    as_user(Role.ANALYST)
    huge = "x" * 200_001
    assert client.post("/api/v1/cases/e1/notes", json={"body": huge}).status_code == 422


def test_read_only_cannot_use_the_case_workbench(client: TestClient) -> None:
    as_user(Role.READ_ONLY)
    base = "/api/v1/cases/e1"
    assert client.post(f"{base}/tasks", json={"title": "x"}).status_code == 403
    assert client.post(f"{base}/documents", files={"file": ("a.txt", b"x")}).status_code == 403
    assert client.put(f"{base}/report", json={"summary": "x"}).status_code == 403
    closing = client.post(f"{base}/close", json={"outcome": "confirmed", "summary": "x"})
    assert closing.status_code == 403


def test_closing_needs_a_known_outcome_and_a_summary(client: TestClient) -> None:
    as_user(Role.ANALYST)
    base = "/api/v1/cases/e1/close"
    assert client.post(base, json={"outcome": "confirmed", "summary": ""}).status_code == 422
    assert client.post(base, json={"summary": "done"}).status_code == 422
    assert client.post(base, json={"outcome": "open", "summary": "done"}).status_code == 422
    bad_date = {"outcome": "confirmed", "summary": "x",
                "authority": {"reported": True, "reported_on": "not a date"}}
    assert client.post(base, json=bad_date).status_code == 422


def test_a_task_needs_a_title(client: TestClient) -> None:
    as_user(Role.ANALYST)
    assert client.post("/api/v1/cases/e1/tasks", json={"title": ""}).status_code == 422
