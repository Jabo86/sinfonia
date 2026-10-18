"""Service: gestisce un job dell'orchestratore in background, con stato in memoria."""
from __future__ import annotations

import asyncio
import shutil
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import orchestrator_engine as engine


@dataclass
class JobStatus:
    running: bool = False
    phase: str = "idle"
    project_dir: str = ""
    model: str = ""
    started_at: str = ""
    finished_at: str = ""
    log: list[str] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    verdict: str = ""
    error: str = ""


class OrchestratorService:
    def __init__(self) -> None:
        self._status = JobStatus()
        self._lock = threading.Lock()
        self._task: asyncio.Task | None = None
        self._stop_flag = False

    # ---------- helpers ----------

    def _log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        with self._lock:
            self._status.log.append(line)
            if len(self._status.log) > 500:
                self._status.log = self._status.log[-500:]

    def _refresh_files(self, project_dir: Path) -> None:
        files = []
        for p in project_dir.rglob("*.py"):
            if ".orchestrator" in str(p) or "__pycache__" in str(p):
                continue
            try:
                st = p.stat()
                files.append({
                    "path": str(p.relative_to(project_dir)),
                    "size": st.st_size,
                    "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                })
            except OSError:
                pass
        files.sort(key=lambda x: x["path"])
        with self._lock:
            self._status.files = files

    # ---------- API ----------

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._status)

    async def start(self, project_dir: str, model: str, requirements: str, clean: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._status.running:
                return {"ok": False, "error": "Job già in esecuzione"}

        pd = Path(project_dir).expanduser().resolve()
        if clean and pd.exists():
            shutil.rmtree(pd)
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "REQUIREMENTS.md").write_text(requirements)
        (pd / ".orchestrator").mkdir(exist_ok=True)

        with self._lock:
            self._status = JobStatus(
                running=True,
                phase="starting",
                project_dir=str(pd),
                model=model,
                started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            self._stop_flag = False

        engine.MODEL = model
        self._log(f"=== START {pd} (model={model}) ===")
        self._task = asyncio.create_task(self._run(pd))
        return {"ok": True, "project_dir": str(pd), "model": model}

    async def _run(self, project_dir: Path) -> None:
        try:
            await asyncio.to_thread(self._run_sync, project_dir)
        except Exception as e:
            with self._lock:
                self._status.error = f"{type(e).__name__}: {e}"
                self._status.phase = "error"
            self._log(f"ERRORE: {e}")
            self._log(traceback.format_exc()[-1000:])
        finally:
            with self._lock:
                self._status.running = False
                self._status.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                if self._status.phase != "error":
                    self._status.phase = "done"
            self._refresh_files(project_dir)
            self._log("=== FINE ===")

    def _run_sync(self, project_dir: Path) -> None:
        state = {
            "requirements": (project_dir / "REQUIREMENTS.md").read_text(),
            "state_path": project_dir / ".orchestrator" / "state.json",
            "log_path": project_dir / ".orchestrator" / "log.txt",
            "project_dir": str(project_dir),
            "phase": "start",
        }
        self._log("PLANNER: leggo REQUIREMENTS.md")
        with self._lock:
            self._status.phase = "planning"
        files = engine.planner(state)
        self._log(f"PLANNER: {len(files)} file da creare")

        with self._lock:
            self._status.phase = "developing"
        for spec in files:
            if self._stop_flag:
                self._log("STOP richiesto, interrompo")
                return
            target = project_dir / spec["path"]
            if target.exists():
                self._log(f"SKIP {spec['path']} (esiste già)")
                continue
            self._log(f"DEVELOPER: scrivo {spec['path']}")
            engine.developer(state, spec, project_dir)
            self._log(f"DEVELOPER: {spec['path']} scritto")
            self._refresh_files(project_dir)

        with self._lock:
            self._status.phase = "testing"
        for attempt in range(1, engine.MAX_FIX_ATTEMPTS + 1):
            if self._stop_flag:
                self._log("STOP richiesto, interrompo")
                return
            ok, out = engine.tester(state, project_dir)
            if ok:
                self._log("TESTER: PASS")
                break
            self._log(f"BUG-FINDER: tentativo {attempt}/{engine.MAX_FIX_ATTEMPTS}")
            if not engine.bug_finder(state, project_dir, out):
                self._log("BUG-FINDER: nessun fix, esco dal loop")
                break
            self._refresh_files(project_dir)

        with self._lock:
            self._status.phase = "reviewing"
        verdict = engine.reviewer(state, project_dir)
        with self._lock:
            self._status.verdict = verdict
        self._log(f"REVIEWER: {verdict[:200]}")


orchestrator_service = OrchestratorService()
