import os
import uuid
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/messages"
)


class MessageIn(BaseModel):
    name: str
    message: str


def get_conn():
    # Used as `with get_conn() as conn:` -> commits on success, always closes
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, message TEXT NOT NULL)"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/messages")
def create_message(item: MessageIn):
    new_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (id, name, message) VALUES (%s, %s, %s)",
            (new_id, item.name, item.message),
        )
    return {"id": new_id, "name": item.name, "message": item.message}


@app.get("/messages")
def list_messages():
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name, message FROM messages").fetchall()
    return rows


@app.get("/messages/{message_id}")
def get_message(message_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, message FROM messages WHERE id = %s", (message_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return row


@app.delete("/messages/{message_id}")
def delete_message(message_id: str):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM messages WHERE id = %s", (message_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Message not found")
    return {"deleted": True, "id": message_id}


@app.get("/health")
def health():
    with get_conn() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}
