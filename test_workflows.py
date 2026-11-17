import pytest
from fastapi.testclient import TestClient

import main

STEPS = [
    {"name": "fetch", "action": "log", "params": {"text": "start"}},
    {"name": "done", "action": "log"},
]


@pytest.fixture()
def client():
    main.init_db()
    with main.get_conn() as conn:
        conn.execute("TRUNCATE messages, workflows")
    return TestClient(main.app)


def make(client, name="demo", steps=STEPS):
    r = client.post("/workflows", json={"name": name, "steps": steps})
    assert r.status_code == 201
    return r.json()


def test_workflows_start_empty(client):
    assert client.get("/workflows").json() == []


def test_create_returns_workflow_with_default_params(client):
    created = make(client)
    assert created["name"] == "demo"
    assert created["steps"][0]["params"] == {"text": "start"}
    assert created["steps"][1]["params"] == {}  # default


def test_create_then_get(client):
    created = make(client)
    r = client.get(f"/workflows/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_list_returns_workflows_in_creation_order(client):
    a = make(client, name="a")
    b = make(client, name="b")
    assert client.get("/workflows").json() == [a, b]


def test_create_rejects_empty_steps(client):
    r = client.post("/workflows", json={"name": "x", "steps": []})
    assert r.status_code == 422


def test_create_rejects_missing_name(client):
    r = client.post("/workflows", json={"steps": STEPS})
    assert r.status_code == 422


def test_create_rejects_step_without_action(client):
    r = client.post("/workflows", json={"name": "x", "steps": [{"name": "s"}]})
    assert r.status_code == 422


def test_get_missing_workflow_is_404(client):
    r = client.get("/workflows/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Workflow not found"}
