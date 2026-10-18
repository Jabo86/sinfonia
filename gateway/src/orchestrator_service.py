from __future__ import annotations
import asyncio, shutil, threading, time, traceback
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
    language: str = "python"
    started_at: str = ""
    finished_at: str = ""
    log: list = field(default_factory=list)
    files: list = field(default_factory=list)
    verdict: str = ""
    error: str = ""

class OrchestratorService:
    def __init__(self):
        self._status = JobStatus()
        self._lock = threading.Lock()
        self._task = None
        self._stop_flag = False

    def _log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        with self._lock:
            self._status.log.append(line)
            if len(self._status.log) > 500: self._status.log = self._status.log[-500:]

    def _refresh_files(self, project_dir):
        try: ext = engine.profile()["ext"]
        except: ext = ".py"
        files = []
        for p in project_dir.rglob("*" + ext):
            if ".orchestrator" in str(p) or "__pycache__" in str(p) or "target" in str(p) or "node_modules" in str(p): continue
            try:
                files.append({"path": str(p.relative_to(project_dir)), "size": p.stat().st_size})
            except: pass
        with self._lock: self._status.files = sorted(files, key=lambda x: x["path"])

    def get_status(self):
        with self._lock: return asdict(self._status)

    async def start(self, project_dir, model, requirements, clean=False, language="python"):
        try:
            with self._lock:
                if self._status.running: return {"ok": False, "error": "Job già in esecuzione"}
            engine.set_language(language)
            pd = Path(project_dir).expanduser().resolve()
            if clean and pd.exists(): shutil.rmtree(pd)
            pd.mkdir(parents=True, exist_ok=True)
            (pd / "REQUIREMENTS.md").write_text(requirements)
            (pd / ".orchestrator").mkdir(exist_ok=True)
            with self._lock:
                self._status = JobStatus(running=True, phase="starting", project_dir=str(pd), model=model, language=language, started_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
                self._stop_flag = False
            engine.MODEL = model
            self._log(f"=== START {pd} (model={model}, lang={language}) ===")
            self._task = asyncio.create_task(self._run(pd))
            return {"ok": True, "project_dir": str(pd), "model": model, "language": language}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)}"}

    async def _run(self, project_dir):
        try:
            await asyncio.to_thread(self._run_sync, project_dir)
        except Exception as e:
            with self._lock:
                self._status.error = f"{type(e).__name__}: {e}"
                self._status.phase = "error"
            self._log(f"ERRORE: {e}")
        finally:
            with self._lock:
                self._status.running = False
                self._status.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                if self._status.phase != "error": self._status.phase = "done"
            self._refresh_files(project_dir)
            self._log("=== FINE ===")

    def _run_sync(self, project_dir):
        state = {"requirements": (project_dir / "REQUIREMENTS.md").read_text(), "project_dir": str(project_dir)}
        self._log("PLANNER: leggo REQUIREMENTS.md")
        with self._lock: self._status.phase = "planning"
        files = engine.planner(state)
        self._log(f"PLANNER: {len(files)} file da creare")

        with self._lock: self._status.phase = "developing"
        for spec in files:
            if self._stop_flag: return
            target = project_dir / spec["path"]
            if target.exists():
                self._log(f"SKIP {spec['path']}")
                continue
            self._log(f"DEVELOPER: scrivo {spec['path']}")
            try:
                engine.developer(state, spec, project_dir)
                self._log(f"DEVELOPER: {spec['path']} scritto")
                self._refresh_files(project_dir)
            except Exception as e:
                self._log(f"DEVELOPER errore: {e}")

        with self._lock: self._status.phase = "testing"
        for attempt in range(1, engine.MAX_FIX_ATTEMPTS + 1):
            if self._stop_flag: return
            ok, out = engine.tester(state, project_dir)
            if ok:
                self._log("TESTER: PASS")
                break
            self._log(f"BUG-FINDER: tentativo {attempt}/{engine.MAX_FIX_ATTEMPTS}")
            if not engine.bug_finder(state, project_dir, out):
                self._log("BUG-FINDER: nessun fix")
                break
            self._refresh_files(project_dir)

        with self._lock: self._status.phase = "reviewing"
        verdict = engine.reviewer(state, project_dir)
        with self._lock: self._status.verdict = verdict
        self._log(f"REVIEWER: {verdict[:200]}")

orchestrator_service = OrchestratorService()
