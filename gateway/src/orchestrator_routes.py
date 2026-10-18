from __future__ import annotations
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from orchestrator_service import orchestrator_service

router = APIRouter(prefix="/v1/orchestrator", tags=["orchestrator"])

class StartRequest(BaseModel):
    project_dir: str
    requirements: str
    model: str = "qwen2.5-coder:7b-32k"
    language: str = "python"
    clean: bool = False

@router.post("/start")
async def start(req: StartRequest) -> dict[str, Any]:
    return await orchestrator_service.start(
        project_dir=req.project_dir, model=req.model, requirements=req.requirements, clean=req.clean, language=req.language
    )

@router.get("/status")
async def status() -> dict[str, Any]:
    return orchestrator_service.get_status()

@router.get("/file")
async def file_content(path: str) -> dict[str, Any]:
    st = orchestrator_service.get_status()
    if not st["project_dir"]: raise HTTPException(404, "Nessun job attivo")
    root = Path(st["project_dir"]).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)): raise HTTPException(400, "Path non valido")
    if not target.exists() or not target.is_file(): raise HTTPException(404, "File non trovato")
    return {"path": path, "content": target.read_text(errors="replace")}

@router.post("/stop")
async def stop() -> dict[str, Any]:
    orchestrator_service._stop_flag = True
    return {"ok": True, "message": "Stop richiesto"}
