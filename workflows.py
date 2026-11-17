import uuid

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from db import get_conn

router = APIRouter(prefix="/workflows", tags=["workflows"])


class StepIn(BaseModel):
    name: str = Field(min_length=1)
    action: str = Field(min_length=1)  # e.g. "log", "http", "ai" (added in later phases)
    params: dict = Field(default_factory=dict)


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1)
    steps: list[StepIn] = Field(min_length=1)


def init_workflows():
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS workflows ("
            "id TEXT PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "steps JSONB NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )


@router.post("", status_code=201)
def create_workflow(item: WorkflowIn):
    new_id = str(uuid.uuid4())
    steps = [s.model_dump() for s in item.steps]
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO workflows (id, name, steps) VALUES (%s, %s, %s)",
            (new_id, item.name, Jsonb(steps)),
        )
    return {"id": new_id, "name": item.name, "steps": steps}


@router.get("")
def list_workflows():
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, name, steps FROM workflows ORDER BY created_at, id"
        ).fetchall()


@router.get("/{workflow_id}")
def get_workflow(workflow_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, steps FROM workflows WHERE id = %s", (workflow_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return row
