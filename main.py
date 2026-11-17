import sqlite3
import uuid
from contextlib import closing

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os

DB_FILE = os.environ.get("DB_FILE", "messages.db")

app = FastAPI()


class MessageIn(BaseModel):
    name: str
    message: str


def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_conn()) as conn:
        with conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id TEXT PRIMARY KEY, name TEXT NOT NULL, message TEXT NOT NULL)"
            )


init_db()


@app.post("/messages")
def create_message(item: MessageIn):
    new_id = str(uuid.uuid4())
    with closing(get_conn()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO messages (id, name, message) VALUES (?, ?, ?)",
                (new_id, item.name, item.message),
            )
    return {"id": new_id, "name": item.name, "message": item.message}


@app.get("/messages")
def list_messages():
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT id, name, message FROM messages").fetchall()
    return [dict(r) for r in rows]

@app.get("/messages/{message_id}")
def get_message(message_id: str):
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT id, name, message FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return dict(row)

@app.delete("/messages/{message_id}")
def delete_message(message_id: str):
    with closing(get_conn()) as conn:
        with conn:
            cur = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Message not found")
    return {"deleted": True, "id": message_id}

@app.get("/health")
def health():
    with closing(get_conn()) as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}
