"""
Sinfonia — Conversation State Manager

Gestisce lo stato delle conversazioni su SQLite per garantire
continuita quando il router cambia provider.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

log = structlog.get_logger()


@dataclass
class Message:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Conversation:
    conversation_id: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationStore:
    """Store persistente per le conversazioni."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages (conversation_id, timestamp)
            """)
            await db.commit()
        self._initialized = True
        log.info("conversation_store.initialized", db_path=str(self.db_path))

    async def create_conversation(self, metadata: dict[str, Any] | None = None) -> str:
        await self._ensure_initialized()
        conv_id = str(uuid.uuid4())
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO conversations (conversation_id, created_at, updated_at, metadata) VALUES (?, ?, ?, ?)",
                (conv_id, now, now, json.dumps(metadata or {})),
            )
            await db.commit()
        log.info("conversation_store.created", conversation_id=conv_id)
        return conv_id

    async def add_message(self, conversation_id: str, role: str, content: str) -> None:
        await self._ensure_initialized()
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, now),
            )
            await db.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (now, conversation_id),
            )
            await db.commit()

    async def get_messages(self, conversation_id: str) -> list[Message]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role, content, timestamp FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC",
                (conversation_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [Message(role=r[0], content=r[1], timestamp=r[2]) for r in rows]

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT conversation_id, created_at, updated_at, metadata FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None
        messages = await self.get_messages(conversation_id)
        return Conversation(
            conversation_id=row[0],
            messages=messages,
            created_at=row[1],
            updated_at=row[2],
            metadata=json.loads(row[3]),
        )
