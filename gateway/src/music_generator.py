"""
Sinfonia — Music Generator

Genera musica con Tunova (Suno v5.5).
Richiede TUNOVA_API_KEY.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()


@dataclass
class MusicResult:
    job_id: str
    status: str
    audio_url: str | None
    title: str
    prompt: str
    provider: str = "tunova"

    def to_dict(self) -> dict:
        return {
            "type": "music",
            "job_id": self.job_id,
            "status": self.status,
            "url": self.audio_url,
            "title": self.title,
            "prompt": self.prompt,
            "provider": self.provider,
        }


class MusicGenerator:
    """
    Genera musica con Tunova (Suno v5.5).
    """

    BASE_URL = "https://api.tunova.ai/v1"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("TUNOVA_API_KEY")
        if not self.api_key:
            log.warning("music.no_api_key", hint="Imposta TUNOVA_API_KEY in .env")

    async def generate(
        self, prompt: str, model: str = "v5.5", title: str = ""
    ) -> MusicResult:
        """
        Avvia la generazione di una canzone.

        Args:
            prompt: descrizione della canzone
            model: modello (v5.5)
            title: titolo opzionale

        Returns:
            MusicResult con job_id
        """
        if not self.api_key:
            raise RuntimeError("TUNOVA_API_KEY non configurata")

        payload = {
            "prompt": prompt,
            "model": model,
        }
        if title:
            payload["title"] = title

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        log.info("music.generate", prompt=prompt[:50], model=model)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/generate", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

        return MusicResult(
            job_id=data.get("id", ""),
            status=data.get("status", "pending"),
            audio_url=None,
            title=title or data.get("title", ""),
            prompt=prompt,
        )

    async def poll(self, job_id: str, max_attempts: int = 60) -> MusicResult:
        """Attende il completamento del brano."""
        if not self.api_key:
            raise RuntimeError("TUNOVA_API_KEY non configurata")

        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(max_attempts):
                resp = await client.get(
                    f"{self.BASE_URL}/jobs/{job_id}", headers=headers
                )
                if resp.status_code != 200:
                    await asyncio.sleep(5)
                    continue

                data = resp.json()
                status = data.get("status", "unknown")

                if status == "complete":
                    clips = data.get("clips", [])
                    url = clips[0].get("audio_url") if clips else None
                    return MusicResult(
                        job_id=job_id,
                        status="complete",
                        audio_url=url,
                        title=data.get("title", ""),
                        prompt=data.get("prompt", ""),
                    )
                elif status in ("failed", "error"):
                    return MusicResult(
                        job_id=job_id, status="failed", audio_url=None,
                        title="", prompt="",
                    )

                await asyncio.sleep(5)

        return MusicResult(
            job_id=job_id, status="timeout", audio_url=None,
            title="", prompt="",
        )

    async def generate_and_wait(self, prompt: str) -> MusicResult:
        """Genera e attende il completamento."""
        job = await self.generate(prompt)
        return await self.poll(job.job_id)
