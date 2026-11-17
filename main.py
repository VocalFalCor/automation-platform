import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_conn
from workflows import init_workflows
from workflows import router as workflows_router


class MessageIn(BaseModel):
    name: str
    message: str


def init_db():
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, message TEXT NOT NULL)"
        )
    init_workflows()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(workflows_router)


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
