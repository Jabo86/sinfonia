"""
Sinfonia — Video Generator

Genera video con InferencePort (proxy OpenAI-compatible, no API key).
Modelli: Wan, Kling, Vidu, Seedance, PixVerse, Hailuo.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()


@dataclass
class VideoResult:
    job_id: str
    status: str
    url: str | None
    prompt: str
    model: str
    provider: str = "inferenceport"

    def to_dict(self) -> dict:
        return {
            "type": "video",
            "job_id": self.job_id,
            "status": self.status,
            "url": self.url,
            "prompt": self.prompt,
            "model": self.model,
            "provider": self.provider,
        }


class VideoGenerator:
    """
    Genera video con InferencePort (API pubblica, nessuna chiave).
    """

    BASE_URL = "https://api.inferenceport.ai/v1"

    def __init__(self, model: str = "wan-fast"):
        self.model = model

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        duration: int = 5,
        resolution: str = "480p",
    ) -> VideoResult:
        """
        Avvia la generazione di un video (async job).

        Returns:
            VideoResult con job_id per il polling
        """
        model = model or self.model
        payload = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "resolution": resolution,
        }

        log.info("video.generate", prompt=prompt[:50], model=model)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.BASE_URL}/videos", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return VideoResult(
            job_id=data.get("id", ""),
            status=data.get("status", "pending"),
            url=None,
            prompt=prompt,
            model=model,
        )

    async def poll(self, job_id: str, max_attempts: int = 60) -> VideoResult:
        """
        Attende il completamento del video e restituisce l'URL.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(max_attempts):
                resp = await client.get(f"{self.BASE_URL}/videos/{job_id}")
                if resp.status_code != 200:
                    await asyncio.sleep(5)
                    continue

                data = resp.json()
                status = data.get("status", "unknown")

                if status == "completed":
                    return VideoResult(
                        job_id=job_id,
                        status="completed",
                        url=data.get("url") or f"{self.BASE_URL}/videos/{job_id}/content",
                        prompt=data.get("prompt", ""),
                        model=data.get("model", self.model),
                    )
                elif status == "failed":
                    return VideoResult(
                        job_id=job_id,
                        status="failed",
                        url=None,
                        prompt=data.get("prompt", ""),
                        model=data.get("model", self.model),
                    )

                await asyncio.sleep(5)

        return VideoResult(
            job_id=job_id, status="timeout", url=None,
            prompt="", model=self.model,
        )

    async def generate_and_wait(
        self, prompt: str, model: str | None = None, duration: int = 5
    ) -> VideoResult:
        """Genera e attende il completamento."""
        job = await self.generate(prompt, model=model, duration=duration)
        return await self.poll(job.job_id)


# Test rapido
if __name__ == "__main__":
    import asyncio

    async def test():
        gen = VideoGenerator()
        result = await gen.generate("un delfino che salta sulle onde")
        print(f"Job ID: {result.job_id}")
        print(f"Status: {result.status}")
        print(f"Polling...")
        final = await gen.poll(result.job_id)
        print(f"Final: {final.status} - {final.url}")

    asyncio.run(test())
