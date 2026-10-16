"""
Sinfonia — Profession Manager
Carica i profili professionali e fornisce il system prompt per ogni richiesta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, Field

log = structlog.get_logger()


class Profession(BaseModel):
    name: str
    icon: str = "🎼"
    description: str = ""
    system_prompt: str
    tools: list[str] = Field(default_factory=list)


class ProfessionsFile(BaseModel):
    version: int = 1
    default: str = "generico"
    professions: dict[str, Profession]


class ProfessionManager:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self._data = None

    def load(self):
        if not self.config_path.exists():
            raise FileNotFoundError(f"File profili non trovato: {self.config_path}")
        with self.config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._data = ProfessionsFile(**data)
        log.info("profession_manager.loaded", count=len(self._data.professions))

    @property
    def professions(self):
        if not self._data:
            self.load()
        return self._data.professions

    def get(self, profession_id):
        if not self._data:
            self.load()
        if profession_id and profession_id in self._data.professions:
            return self._data.professions[profession_id]
        return self._data.professions[self._data.default]

    def get_system_prompt(self, profession_id=None):
        return self.get(profession_id).system_prompt

    def list_all(self):
        if not self._data:
            self.load()
        return [
            {
                "id": pid,
                "name": p.name,
                "icon": p.icon,
                "description": p.description,
                "tools": p.tools,
            }
            for pid, p in self._data.professions.items()
        ]


_manager = None


def get_profession_manager():
    global _manager
    if _manager is None:
        path = Path(__file__).resolve().parent.parent.parent / "config" / "professions.yaml"
        _manager = ProfessionManager(path)
    return _manager


if __name__ == "__main__":
    pm = get_profession_manager()
    profs = pm.list_all()
    print(f"Profili caricati: {len(profs)}")
    for p in profs:
        print(f"  {p['icon']} {p['name']:12} ({p['id']}) - {p['description']}")
