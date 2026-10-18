"""
Sinfonia — Quota Manager

Traccia le quote residue di ogni provider su SQLite.
Non aggira MAI i limiti: se una quota e esaurita, il provider viene
marcato come non disponibile fino al reset della finestra.

Questo e il cuore della conformita ai ToS di Sinfonia.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

log = structlog.get_logger()


# --- Costanti --------------------------------------------------------------

WINDOW_RPM = 60          # finestra RPM in secondi
WINDOW_RPD = 86400       # finestra RPD in secondi
COOLDOWN_429_SECONDS = 60  # cooldown dopo un 429 (default prudenziale)

# Provider con reset a mezzanotte (fuso orario reale del provider)
RESET_AT_MIDNIGHT = {
    "groq": "UTC",                  # 00:00 UTC = 02:00 IT
    "google_gemini": "US/Pacific",  # 00:00 PT  = 09:00 IT
}


# --- Helper: inizio finestra giornaliera -----------------------------------

def _get_day_start(provider_id: str, now: float) -> float:
    """
    Ritorna il timestamp unix dell'inizio della finestra giornaliera (RPD)
    per il provider indicato.

    - Se il provider compare in RESET_AT_MIDNIGHT, ritorna la mezzanotte
      del giorno corrente nel suo fuso orario, espresso come timestamp unix.
    - Altrimenti usa una rolling window di 24h (WINDOW_RPD).

    `now` è un timestamp unix (float), coerente con time.time().
    """
    tz_name = RESET_AT_MIDNIGHT.get(provider_id)
    if tz_name is None:
        return now - WINDOW_RPD
    tz = ZoneInfo(tz_name)
    local_now = datetime.fromtimestamp(now, tz=tz)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.timestamp()


# --- Modello dati ----------------------------------------------------------

@dataclass
class QuotaStatus:
    """Stato corrente di un provider."""
    provider_id: str
    requests_this_minute: int
    requests_today: int
    tokens_today: int
    rpm_limit: int | None
    rpd_limit: int | None
    tpd_limit: int | None
    cooldown_until: float | None  # timestamp unix, se in cooldown
    last_429_at: float | None

    @property
    def is_in_cooldown(self) -> bool:
        if self.cooldown_until is None:
            return False
        return time.time() < self.cooldown_until

    @property
    def cooldown_remaining(self) -> int:
        if not self.is_in_cooldown:
            return 0
        return int(self.cooldown_until - time.time())

    @property
    def has_rpm_capacity(self) -> bool:
        if self.rpm_limit is None:
            return True
        return self.requests_this_minute < self.rpm_limit

    @property
    def has_rpd_capacity(self) -> bool:
        if self.rpd_limit is None:
            return True
        return self.requests_today < self.rpd_limit

    @property
    def has_tpd_capacity(self) -> bool:
        if self.tpd_limit is None:
            return True
        return self.tokens_today < self.tpd_limit

    @property
    def is_available(self) -> bool:
        """Un provider e disponibile solo se NON in cooldown e con capacita residua."""
        if self.is_in_cooldown:
            return False
        return self.has_rpm_capacity and self.has_rpd_capacity and self.has_tpd_capacity

    @property
    def free_capacity_score(self) -> int:
        """Punteggio per il routing quota-aware. Piu alto = piu quota residua."""
        score = 0
        if self.rpm_limit:
            score += (self.rpm_limit - self.requests_this_minute) * 1000
        if self.rpd_limit:
            score += (self.rpd_limit - self.requests_today) * 10
        if self.tpd_limit:
            score += max(0, self.tpd_limit - self.tokens_today) // 1000
        return max(0, score)


# --- Quota Manager ---------------------------------------------------------

class QuotaManager:
    """
    Gestisce le quote di tutti i provider su SQLite.

    Regole ferree:
    - Non superare MAI un limite dichiarato.
    - Se un provider risponde 429, entra in cooldown.
    - Le quote sono per (provider_id, user_id). Default user: "local".
    """

    def __init__(self, db_path: str | Path, user_id: str = "local"):
        self.db_path = Path(db_path)
        self.user_id = user_id
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        tokens INTEGER NOT NULL DEFAULT 0,
                        status_code INTEGER,
                        was_429 INTEGER NOT NULL DEFAULT 0
                    )
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_requests_provider_time
                    ON requests (provider_id, user_id, timestamp)
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS cooldowns (
                        provider_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        cooldown_until REAL NOT NULL,
                        last_429_at REAL NOT NULL,
                        PRIMARY KEY (provider_id, user_id)
                    )
                """)
                await db.commit()
            self._initialized = True
            log.info("quota_manager.initialized", db_path=str(self.db_path))

    async def record_request(
        self,
        provider_id: str,
        tokens: int = 0,
        status_code: int | None = None,
        was_429: bool = False,
    ) -> None:
        """Registra una richiesta fatta a un provider."""
        await self._ensure_initialized()
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO requests (provider_id, user_id, timestamp, tokens, status_code, was_429)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (provider_id, self.user_id, now, tokens, status_code, 1 if was_429 else 0),
            )
            if was_429:
                cooldown_until = now + COOLDOWN_429_SECONDS
                await db.execute(
                    """
                    INSERT INTO cooldowns (provider_id, user_id, cooldown_until, last_429_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(provider_id, user_id) DO UPDATE SET
                        cooldown_until = excluded.cooldown_until,
                        last_429_at = excluded.last_429_at
                    """,
                    (provider_id, self.user_id, cooldown_until, now),
                )
                log.warning(
                    "quota_manager.429_recorded",
                    provider=provider_id,
                    cooldown_seconds=COOLDOWN_429_SECONDS,
                )
            await db.commit()

    async def get_status(
        self,
        provider_id: str,
        rpm_limit: int | None = None,
        rpd_limit: int | None = None,
        tpd_limit: int | None = None,
    ) -> QuotaStatus:
        """Restituisce lo stato corrente di un provider."""
        await self._ensure_initialized()
        now = time.time()
        minute_ago = now - WINDOW_RPM
        day_ago = _get_day_start(provider_id, now)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT COUNT(*) FROM requests
                WHERE provider_id = ? AND user_id = ? AND timestamp >= ?
                """,
                (provider_id, self.user_id, minute_ago),
            ) as cur:
                requests_this_minute = (await cur.fetchone())[0]

            async with db.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(tokens), 0) FROM requests
                WHERE provider_id = ? AND user_id = ? AND timestamp >= ?
                """,
                (provider_id, self.user_id, day_ago),
            ) as cur:
                row = await cur.fetchone()
                requests_today, tokens_today = row[0], row[1]

            cooldown_until = None
            last_429_at = None
            async with db.execute(
                """
                SELECT cooldown_until, last_429_at FROM cooldowns
                WHERE provider_id = ? AND user_id = ?
                """,
                (provider_id, self.user_id),
            ) as cur:
                cooldown_row = await cur.fetchone()
                if cooldown_row:
                    cooldown_until, last_429_at = cooldown_row

        return QuotaStatus(
            provider_id=provider_id,
            requests_this_minute=requests_this_minute,
            requests_today=requests_today,
            tokens_today=tokens_today,
            rpm_limit=rpm_limit,
            rpd_limit=rpd_limit,
            tpd_limit=tpd_limit,
            cooldown_until=cooldown_until,
            last_429_at=last_429_at,
        )

    async def get_all_statuses(
        self,
        providers_limits: dict[str, dict[str, int | None]],
    ) -> dict[str, QuotaStatus]:
        """Restituisce lo stato di tutti i provider in una sola query."""
        statuses = {}
        for provider_id, limits in providers_limits.items():
            statuses[provider_id] = await self.get_status(
                provider_id,
                rpm_limit=limits.get("rpm"),
                rpd_limit=limits.get("rpd"),
                tpd_limit=limits.get("tpd") or limits.get("tokens_per_day"),
            )
        return statuses

    async def cleanup_old_records(self, older_than_seconds: int = 7 * 86400) -> int:
        """Rimuove le richieste piu vecchie di N secondi. Ritorna il numero rimosso."""
        await self._ensure_initialized()
        cutoff = time.time() - older_than_seconds
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM requests WHERE timestamp < ?", (cutoff,)
            )
            await db.commit()
            deleted = cur.rowcount
        log.info("quota_manager.cleanup", deleted=deleted)
        return deleted


# --- Test rapido -----------------------------------------------------------

async def _test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        qm = QuotaManager(Path(tmpdir) / "test.db")

        # Provider con limiti
        status = await qm.get_status("groq", rpm_limit=30, rpd_limit=14400)
        assert status.is_available, "Groq dovrebbe essere disponibile"
        assert status.free_capacity_score > 0

        # Registra 5 richieste
        for _ in range(5):
            await qm.record_request("groq", tokens=100, status_code=200)

        status = await qm.get_status("groq", rpm_limit=30, rpd_limit=14400)
        assert status.requests_this_minute == 5
        assert status.requests_today == 5
        assert status.tokens_today == 500
        assert status.is_available

        # Simula un 429
        await qm.record_request("groq", status_code=429, was_429=True)
        status = await qm.get_status("groq", rpm_limit=30, rpd_limit=14400)
        assert status.is_in_cooldown, "Groq dovrebbe essere in cooldown"
        assert not status.is_available

        print("Test quota_manager: OK")
        print(f"  - RPM: {status.requests_this_minute}/30")
        print(f"  - RPD: {status.requests_today}/14400")
        print(f"  - Cooldown residuo: {status.cooldown_remaining}s")


if __name__ == "__main__":
    asyncio.run(_test())