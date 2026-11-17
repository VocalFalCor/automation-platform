"""Workflow worker.

Claims a run, executes its steps in order, and saves a checkpoint (current_step +
results) after every step. If a worker dies mid-run, the run's heartbeat goes stale
and another worker claims it and resumes at the saved checkpoint, not step 0.

Delivery is at-least-once: a step that was running when the worker died runs again.
Keep each step shorter than LEASE_SECONDS.

Run as a service:  python engine.py
"""
import os
import time

from psycopg.types.json import Jsonb

from db import get_conn

LEASE_SECONDS = float(os.environ.get("RUN_LEASE_SECONDS", "30"))
POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "1"))


class StepError(Exception):
    pass


def execute_step(step: dict) -> dict:
    action = step["action"]
    params = step.get("params", {})
    if action == "log":
        return {"logged": params.get("text", "")}
    if action == "sleep":
        seconds = float(params.get("seconds", 1))
        time.sleep(seconds)
        return {"slept": seconds}
    if action == "fail":
        raise StepError(params.get("reason", "step failed"))
    raise StepError(f"unknown action: {action}")


CLAIM_SQL = """
UPDATE runs SET status = 'running', heartbeat = now(), updated_at = now()
WHERE id = (
    SELECT id FROM runs
    WHERE status = 'pending'
       OR (status = 'running' AND heartbeat < now() - (%s * interval '1 second'))
    ORDER BY created_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, workflow_id, current_step
"""


def claim_run():
    with get_conn() as conn:
        return conn.execute(CLAIM_SQL, (LEASE_SECONDS,)).fetchone()


def _fail(run_id: str, message: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET status = 'failed', error = %s, updated_at = now() "
            "WHERE id = %s",
            (message, run_id),
        )


def process_run(run: dict):
    run_id = run["id"]
    with get_conn() as conn:
        wf = conn.execute(
            "SELECT steps FROM workflows WHERE id = %s", (run["workflow_id"],)
        ).fetchone()
    if wf is None:
        _fail(run_id, "workflow not found")
        return
    steps = wf["steps"]

    for i in range(run["current_step"], len(steps)):
        step = steps[i]
        try:
            result = execute_step(step)
        except Exception as exc:  # a crash (BaseException) is NOT caught: it resumes later
            _fail(run_id, f"step {i} ({step['name']}): {exc}")
            return
        entry = {"step": i, "name": step["name"], "result": result}
        with get_conn() as conn:  # checkpoint
            conn.execute(
                "UPDATE runs SET current_step = %s, results = results || %s, "
                "heartbeat = now(), updated_at = now() WHERE id = %s",
                (i + 1, Jsonb([entry]), run_id),
            )

    with get_conn() as conn:
        conn.execute(
            "UPDATE runs SET status = 'done', updated_at = now() WHERE id = %s",
            (run_id,),
        )


def work_once() -> bool:
    run = claim_run()
    if run is None:
        return False
    process_run(run)
    return True


def run_forever():
    print("worker started", flush=True)
    while True:
        if not work_once():
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
