import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client():
    # Real Postgres (see docker-compose.yml); start each test with an empty table
    main.init_db()
    with main.get_conn() as conn:
        conn.execute("TRUNCATE messages")
    return TestClient(main.app)


def create(client, name="Jasen", message="hello"):
    r = client.post("/messages", json={"name": name, "message": message})
    assert r.status_code == 200
    return r.json()


def test_list_starts_empty(client):
    r = client.get("/messages")
    assert r.status_code == 200
    assert r.json() == []


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_list(client):
    created = create(client, message="Postgres test")
    r = client.get("/messages")
    assert r.json() == [created]


def test_delete_existing(client):
    created = create(client)
    r = client.delete(f"/messages/{created['id']}")
    assert r.status_code == 200
    assert r.json() == {"deleted": True, "id": created["id"]}
    assert client.get("/messages").json() == []


def test_delete_missing_returns_404(client):
    r = client.delete("/messages/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Message not found"}


def test_delete_twice_second_is_404(client):
    created = create(client)
    assert client.delete(f"/messages/{created['id']}").status_code == 200
    assert client.delete(f"/messages/{created['id']}").status_code == 404


def test_delete_only_removes_target(client):
    a = create(client, message="a")
    b = create(client, message="b")
    client.delete(f"/messages/{a['id']}")
    assert client.get("/messages").json() == [b]


def test_no_connection_leak_after_many_requests(client):
    # Regression test: every request must close its connection
    ids = [create(client, message=str(i))["id"] for i in range(25)]
    for _ in range(5):
        client.get("/messages")
    for message_id in ids:
        assert client.delete(f"/messages/{message_id}").status_code == 200
    assert client.get("/messages").json() == []


def test_create_rejects_bad_body(client):
    r = client.post("/messages", json={"name": "only name"})
    assert r.status_code == 422


def test_get_existing_message(client):
    created = create(client, name="jase", message="hi")
    r = client.get(f"/messages/{created['id']}")
    assert r.status_code == 200
    assert r.json() == {"id": created["id"], "name": "jase", "message": "hi"}


def test_get_missing_message_returns_404(client):
    assert client.get("/messages/does-not-exist").status_code == 404
