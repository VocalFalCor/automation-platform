import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/messages"
)


def get_conn():
    # Used as `with get_conn() as conn:` -> commits on success, always closes
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)
