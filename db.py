import os
import sqlite3
import sys
from datetime import datetime


def _db_path() -> str:
    if hasattr(sys, "_MEIPASS"):
        data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DataClarify")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "tracker.db")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS DowntimeEvent (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            startTime        TIMESTAMP NOT NULL,
            endTime          TIMESTAMP,
            duration         REAL,
            Machine_ID       TEXT NOT NULL,
            OperatorComment  TEXT,
            category_id      INTEGER REFERENCES DowntimeCategory(id)
        );

        CREATE TABLE IF NOT EXISTS DowntimeCategory (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL UNIQUE
        );

        INSERT OR IGNORE INTO DowntimeCategory (label) VALUES
            ('Head worn'),
            ('Toner empty'),
            ('Material jam'),
            ('Planned maintenance'),
            ('Other');
    """)
    conn.commit()
    conn.close()


def start_downtime_event(machine_id: str, start_time: datetime) -> int:
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO DowntimeEvent (startTime, Machine_ID) VALUES (?, ?)",
        (start_time.isoformat(), machine_id),
    )
    event_id = cur.lastrowid
    conn.commit()
    conn.close()
    return event_id


def end_downtime_event(event_id: int, end_time: datetime) -> None:
    conn = _connect()
    row = conn.execute("SELECT startTime FROM DowntimeEvent WHERE id = ?", (event_id,)).fetchone()
    if row:
        start = datetime.fromisoformat(row["startTime"])
        # Strip tzinfo for subtraction if needed
        end_naive = end_time.replace(tzinfo=None) if end_time.tzinfo else end_time
        start_naive = start.replace(tzinfo=None) if start.tzinfo else start
        duration = (end_naive - start_naive).total_seconds()
        conn.execute(
            "UPDATE DowntimeEvent SET endTime = ?, duration = ? WHERE id = ?",
            (end_time.isoformat(), duration, event_id),
        )
        conn.commit()
    conn.close()


def get_events(machine_id: str, start_date=None, end_date=None) -> list[dict]:
    conn = _connect()
    query = """
        SELECT e.id, e.startTime, e.endTime, e.duration,
               e.Machine_ID, e.OperatorComment, c.label AS category
        FROM DowntimeEvent e
        LEFT JOIN DowntimeCategory c ON e.category_id = c.id
        WHERE e.Machine_ID = ?
    """
    params: list = [machine_id]
    if start_date:
        query += " AND DATE(e.startTime) >= ?"
        params.append(str(start_date))
    if end_date:
        query += " AND DATE(e.startTime) <= ?"
        params.append(str(end_date))
    query += " ORDER BY e.startTime DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_categories() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT id, label FROM DowntimeCategory ORDER BY label").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_event_comment(event_id: int, comment: str, category_id: int | None) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE DowntimeEvent SET OperatorComment = ?, category_id = ? WHERE id = ?",
        (comment or None, category_id, event_id),
    )
    conn.commit()
    conn.close()
