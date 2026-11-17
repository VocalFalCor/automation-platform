import uuid

from fastapi import APIRouter, HTTPException

from db import get_conn

router = APIRouter(tags=["runs"])

RUN_COLUMNS = "id, workflow_id, status, current_step, results, error"


def init_runs():
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS runs ("
            "id TEXT PRIMARY KEY, "
            "workflow_id TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'pending', "  # pending|running|done|failed
            "current_step INT NOT NULL DEFAULT 0, "  # the checkpoint: next step to run
            "results JSONB NOT NULL DEFAULT '[]', "
            "error TEXT, "
            "heartbeat TIMESTAMPTZ, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )


@router.post("/workflows/{workflow_id}/run", status_code=202)
def start_run(workflow_id: str):
    run_id = str(uuid.uuid4())
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM workflows WHERE id = %s", (workflow_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        run = conn.execute(
            f"INSERT INTO runs (id, workflow_id) VALUES (%s, %s) RETURNING {RUN_COLUMNS}",
            (run_id, workflow_id),
        ).fetchone()
    return run


@router.get("/runs")
def list_runs():
    with get_conn() as conn:
        return conn.execute(
            f"SELECT {RUN_COLUMNS} FROM runs ORDER BY created_at, id"
        ).fetchall()


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {RUN_COLUMNS} FROM runs WHERE id = %s", (run_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return row
