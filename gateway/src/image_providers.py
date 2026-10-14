"""
Sinfonia — Multi-Provider Image Generation

Supporta Cloudflare Workers AI, NVIDIA NIM, Hugging Face Inference.
Router intelligente che sceglie il provider migliore disponibile.
"""

from __future__ import annotations

import asyncio
import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


@dataclass
class ImageResult:
    url: str | None
    b64_data: str | None
    prompt: str
    model: str
    provider: str
    width: int = 1024
    height: int = 1024

    def to_dict(self) -> dict:
        result = {
            "type": "image",
            "prompt": self.prompt,
            "model": self.model,
            "provider": self.provider,
            "width": self.width,
            "height": self.height,
        }
        if self.url:
            result["url"] = self.url
        if self.b64_data:
            result["b64_data"] = self.b64_data
            result["url"] = f"data:image/png;base64,{self.b64_data}"
        return result


class ImageProviderBase:
    name: str = "base"

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024, **kwargs) -> ImageResult:
        raise NotImplementedError


class CloudflareProvider(ImageProviderBase):
    """Cloudflare Workers AI — FLUX.1 Schnell. Free: 10k neuroni/giorno."""

    name = "cloudflare"

    def __init__(self):
        self.api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
        self.account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")

    @property
    def is_available(self) -> bool:
        return bool(self.api_token and self.account_id)

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024, **kwargs) -> ImageResult:
        if not self.is_available:
            raise RuntimeError("Cloudflare non configurato (manca CLOUDFLARE_API_TOKEN o CLOUDFLARE_ACCOUNT_ID)")

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        payload = {"prompt": prompt, "width": width, "height": height}

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Cloudflare restituisce base64 nel JSON
        b64 = None
        if "result" in data and "image" in data["result"]:
            b64 = data["result"]["image"]
        elif "result" in data and isinstance(data["result"], str):
            b64 = data["result"]

        return ImageResult(
            url=None, b64_data=b64, prompt=prompt,
            model="flux-1-schnell", provider=self.name,
            width=width, height=height,
        )


class NvidiaProvider(ImageProviderBase):
    """NVIDIA NIM — FLUX.1-schnell. Free: 40 RPM."""

    name = "nvidia"

    def __init__(self):
        self.api_key = os.environ.get("NVIDIA_API_KEY")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024, **kwargs) -> ImageResult:
        if not self.is_available:
            raise RuntimeError("NVIDIA NIM non configurato (manca NVIDIA_API_KEY)")

        url = "https://integrate.api.nvidia.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "black-forest-labs/flux.1-schnell",
            "prompt": prompt,
            "width": width,
            "height": height,
            "n": 1,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        item = data["data"][0]
        url_out = item.get("url")
        b64 = item.get("b64_json")

        return ImageResult(
            url=url_out, b64_data=b64, prompt=prompt,
            model="flux.1-schnell", provider=self.name,
            width=width, height=height,
        )


class HuggingFaceProvider(ImageProviderBase):
    """Hugging Face Inference — FLUX.1-dev. Free: ~1000 req/day."""

    name = "huggingface"

    def __init__(self):
        self.api_key = os.environ.get("HF_TOKEN")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024, **kwargs) -> ImageResult:
        if not self.is_available:
            raise RuntimeError("Hugging Face non configurato (manca HF_TOKEN)")

        url = "https://router.huggingface.co/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "black-forest-labs/FLUX.1-dev",
            "prompt": prompt,
            "width": width,
            "height": height,
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Formato OpenAI-compatible
        item = data.get("data", [{}])[0]
        return ImageResult(
            url=item.get("url"), b64_data=item.get("b64_json"),
            prompt=prompt, model="FLUX.1-dev", provider=self.name,
            width=width, height=height,
        )




class PollinationsProvider(ImageProviderBase):
    """Pollinations.ai — Flux. Gratis, senza chiave API."""

    name = "pollinations"

    def __init__(self):
        pass

    @property
    def is_available(self) -> bool:
        return True  # sempre disponibile, no chiave

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024, **kwargs) -> ImageResult:
        import urllib.parse
        encoded = urllib.parse.quote(prompt)
        params = urllib.parse.urlencode({
            "width": str(width),
            "height": str(height),
            "model": "flux",
            "nologo": "true",
            "seed": str(hash(prompt) % 1000000),
        })
        url = f"https://image.pollinations.ai/prompt/{encoded}?{params}"

        return ImageResult(
            url=url, b64_data=None, prompt=prompt,
            model="flux", provider=self.name,
            width=width, height=height,
        )


class ImageRouter:
    """
    Router che sceglie il provider di immagini migliore disponibile.
    Ordine di preferenza: NVIDIA → HuggingFace → Cloudflare.
    """

    def __init__(self):
        self.providers: dict[str, ImageProviderBase] = {
            "nvidia": NvidiaProvider(),
            "huggingface": HuggingFaceProvider(),
            "cloudflare": CloudflareProvider(),
            "pollinations": PollinationsProvider(),
        }
        self._cooldowns: dict[str, float] = {}

    def _is_in_cooldown(self, provider: str) -> bool:
        import time
        if provider in self._cooldowns:
            if time.time() < self._cooldowns[provider]:
                return True
            del self._cooldowns[provider]
        return False

    def _mark_cooldown(self, provider: str, seconds: float = 60.0) -> None:
        import time
        self._cooldowns[provider] = time.time() + seconds
        log.warning("image_router.cooldown", provider=provider, seconds=seconds)

    def available_providers(self) -> list[str]:
        return [
            name for name, p in self.providers.items()
            if p.is_available and not self._is_in_cooldown(name)
        ]

    async def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        preferred: str | None = None,
    ) -> ImageResult:
        """
        Genera un'immagine, provando i provider in ordine di preferenza.
        """
        # Ordine: preferred → nvidia → huggingface → cloudflare
        order = []
        if preferred and preferred in self.providers:
            order.append(preferred)
        for name in ["nvidia", "huggingface", "cloudflare", "pollinations"]:
            if name not in order:
                order.append(name)

        last_error = None
        for name in order:
            provider = self.providers[name]
            if not provider.is_available:
                log.debug("image_router.skip_not_configured", provider=name)
                continue
            if self._is_in_cooldown(name):
                log.debug("image_router.skip_cooldown", provider=name)
                continue

            try:
                log.info("image_router.attempt", provider=name, prompt=prompt[:60])
                result = await provider.generate(prompt, width=width, height=height)
                log.info("image_router.success", provider=name)
                return result
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                log.warning("image_router.http_error", provider=name, status=status)
                if status == 429:
                    self._mark_cooldown(name, 60.0)
                last_error = e
                continue
            except Exception as e:
                log.warning("image_router.error", provider=name, error=str(e)[:200])
                last_error = e
                continue

        raise RuntimeError(f"Nessun provider di immagini disponibile. Ultimo errore: {last_error}")


# Test rapido
if __name__ == "__main__":
    import asyncio

    async def test():
        router = ImageRouter()
        print(f"Provider disponibili: {router.available_providers()}")
        if router.available_providers():
            result = await router.generate("un leone maestoso nella savana al tramonto")
            print(f"Provider: {result.provider}")
            print(f"URL: {result.url[:100] if result.url else None}")

    asyncio.run(test())
