from fastapi import APIRouter
from pydantic import BaseModel
import sqlite3
from pathlib import Path

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])
DB_PATH = Path.home() / "sinfonia/data/sinfonia.db"

class Event(BaseModel):
    title: str
    date: str
    time: str | None = None
    description: str | None = None
    type: str = "impegno"

class Alarm(BaseModel):
    time: str
    label: str = "Sveglia"

@router.post("/add")
async def add_event(event: Event):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO events (title, date, time, description, type) VALUES (?, ?, ?, ?, ?)", (event.title, event.date, event.time, event.description, event.type))
    conn.commit(); conn.close()
    return {"ok": True}

@router.get("/list")
async def list_events():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, date, time, description, type FROM events ORDER BY date, time")
    rows = c.fetchall(); conn.close()
    return {"events": [{"id": r[0], "title": r[1], "date": r[2], "time": r[3], "description": r[4], "type": r[5]} for r in rows]}

@router.delete("/delete/{event_id}")
async def delete_event(event_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit(); conn.close()
    return {"ok": True}

@router.post("/alarms")
async def add_alarm(alarm: Alarm):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS alarms (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, label TEXT, active INTEGER DEFAULT 1)")
    c.execute("INSERT INTO alarms (time, label) VALUES (?, ?)", (alarm.time, alarm.label))
    conn.commit(); conn.close()
    return {"ok": True}

@router.get("/alarms")
async def list_alarms():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS alarms (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, label TEXT, active INTEGER DEFAULT 1)")
    c.execute("SELECT id, time, label FROM alarms WHERE active = 1 ORDER BY time")
    rows = c.fetchall(); conn.close()
    return {"alarms": [{"id": r[0], "time": r[1], "label": r[2]} for r in rows]}

@router.delete("/alarms/{alarm_id}")
async def delete_alarm(alarm_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
    conn.commit(); conn.close()
    return {"ok": True}
