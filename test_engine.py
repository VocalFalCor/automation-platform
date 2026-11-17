import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

import engine
import main


class Crash(BaseException):
    """Simulates a worker process dying mid-step (not caught by the engine)."""


@pytest.fixture()
def client():
    main.init_db()
    with main.get_conn() as conn:
        conn.execute("TRUNCATE messages, workflows, runs")
    return TestClient(main.app)


def make_workflow(client, n=4, actions=None):
    actions = actions or ["log"] * n
    steps = [
        {"name": f"s{i}", "action": a, "params": {"text": f"s{i}"}}
        for i, a in enumerate(actions)
    ]
    r = client.post("/workflows", json={"name": "wf", "steps": steps})
    assert r.status_code == 201
    return r.json()


def start(client, wf):
    r = client.post(f"/workflows/{wf['id']}/run")
    assert r.status_code == 202
    return r.json()["id"]


def get_run(client, run_id):
    return client.get(f"/runs/{run_id}").json()


def backdate_heartbeat(run_id):
    with main.get_conn() as conn:
        conn.execute(
            "UPDATE runs SET heartbeat = now() - interval '1 hour' WHERE id = %s",
            (run_id,),
        )


def test_start_run_is_pending(client):
    wf = make_workflow(client)
    r = client.post(f"/workflows/{wf['id']}/run")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    assert body["current_step"] == 0
    assert body["results"] == []


def test_start_run_for_missing_workflow_is_404(client):
    assert client.post("/workflows/nope/run").status_code == 404


def test_get_missing_run_is_404(client):
    assert client.get("/runs/nope").status_code == 404


def test_work_once_with_nothing_to_do(client):
    assert engine.work_once() is False


def test_run_completes_all_steps(client):
    run_id = start(client, make_workflow(client, n=3))
    assert engine.work_once() is True
    run = get_run(client, run_id)
    assert run["status"] == "done"
    assert run["current_step"] == 3
    assert run["results"] == [
        {"step": i, "name": f"s{i}", "result": {"logged": f"s{i}"}} for i in range(3)
    ]
    assert engine.work_once() is False  # nothing left


def test_failing_step_marks_run_failed_at_that_step(client):
    wf = make_workflow(client, actions=["log", "fail", "log"])
    run_id = start(client, wf)
    engine.work_once()
    run = get_run(client, run_id)
    assert run["status"] == "failed"
    assert run["current_step"] == 1
    assert "step 1" in run["error"]
    assert len(run["results"]) == 1


def test_unknown_action_fails_run(client):
    wf = make_workflow(client, actions=["nope"])
    run_id = start(client, wf)
    engine.work_once()
    run = get_run(client, run_id)
    assert run["status"] == "failed"
    assert "unknown action" in run["error"]


def test_fresh_running_run_is_not_claimed(client):
    run_id = start(client, make_workflow(client))
    with main.get_conn() as conn:
        conn.execute(
            "UPDATE runs SET status = 'running', heartbeat = now() WHERE id = %s",
            (run_id,),
        )
    assert engine.work_once() is False


def test_resume_from_checkpoint(client, monkeypatch):
    run_id = start(client, make_workflow(client, n=4))
    done = [
        {"step": i, "name": f"s{i}", "result": {"logged": f"s{i}"}} for i in range(2)
    ]
    with main.get_conn() as conn:
        conn.execute(
            "UPDATE runs SET status = 'running', current_step = 2, results = %s, "
            "heartbeat = now() - interval '1 hour' WHERE id = %s",
            (Jsonb(done), run_id),
        )
    seen = []
    real = engine.execute_step
    monkeypatch.setattr(
        engine, "execute_step", lambda step: (seen.append(step["name"]), real(step))[1]
    )
    assert engine.work_once() is True
    assert seen == ["s2", "s3"]  # steps 0 and 1 were NOT re-run
    run = get_run(client, run_id)
    assert run["status"] == "done"
    assert run["current_step"] == 4
    assert len(run["results"]) == 4


def test_worker_crash_then_another_worker_resumes(client, monkeypatch):
    """The Phase 1 gate: kill the worker mid-run, resume from the last step."""
    run_id = start(client, make_workflow(client, n=4))
    real = engine.execute_step

    def crash_on_step_2(step):
        if step["name"] == "s2":
            raise Crash()
        return real(step)

    monkeypatch.setattr(engine, "execute_step", crash_on_step_2)
    with pytest.raises(Crash):
        engine.work_once()

    # worker "died": run is stuck in 'running' with a checkpoint after step 1
    run = get_run(client, run_id)
    assert run["status"] == "running"
    assert run["current_step"] == 2
    assert len(run["results"]) == 2

    # a second worker does nothing until the lease expires...
    monkeypatch.setattr(engine, "execute_step", real)
    assert engine.work_once() is False

    # ...then picks it up and finishes from step 2
    backdate_heartbeat(run_id)
    seen = []
    monkeypatch.setattr(
        engine, "execute_step", lambda step: (seen.append(step["name"]), real(step))[1]
    )
    assert engine.work_once() is True
    assert seen == ["s2", "s3"]
    run = get_run(client, run_id)
    assert run["status"] == "done"
    assert [r["step"] for r in run["results"]] == [0, 1, 2, 3]
