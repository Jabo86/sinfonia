"""
Sinfonia — Multi-Provider Image Generation

Supporta Google Gemini (text-to-image E image editing), Cloudflare Workers AI,
NVIDIA NIM, Hugging Face Inference, Pollinations.

Router intelligente: se il modello richiesto è Gemini lo usa in modo esplicito;
se c'è un'immagine in input (editing), solo Gemini è in grado di gestirla.
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
    mime_type: str = "image/png"

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
            result["url"] = f"data:{self.mime_type};base64,{self.b64_data}"
        return result


class ImageProviderBase:
    name: str = "base"

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024, **kwargs) -> ImageResult:
        raise NotImplementedError


class GeminiImageProvider(ImageProviderBase):
    """
    Google Gemini image generation + editing via generateContent REST API.

    Modalità:
    - text-to-image: solo prompt -> immagine
    - image editing:  prompt + immagine -> immagine modificata

    Modelli supportati (esempi):
    - gemini-2.5-flash-image
    - gemini-3-pro-image
    - gemini-3.1-flash-image
    """

    name = "google_gemini"
    DEFAULT_MODEL = "gemini-2.5-flash-image"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, config: Any = None):
        self.config = config

    @property
    def api_key(self) -> str | None:
        # 1) config di Sinfonia (get_api_key è già usato altrove nel progetto)
        if self.config is not None and hasattr(self.config, "get_api_key"):
            try:
                key = self.config.get_api_key("google_gemini")
                if key:
                    return key
            except Exception:
                pass
        # 2) variabili d'ambiente comuni
        return (
            os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_GEMINI_API_KEY")
        )

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def _normalize_model(self, model: str | None) -> str:
        """Accetta 'sinfonia/google_gemini/models/xyz', 'google_gemini/xyz' o 'xyz'."""
        if not model:
            return self.DEFAULT_MODEL
        if "/models/" in model:
            return model.split("/models/", 1)[1]
        if model.startswith("google_gemini/"):
            return model.split("/", 1)[1]
        return model

    def _prepare_image_part(self, image: str) -> dict:
        """Trasforma base64 / data URI / URL in un part inline_data per Gemini."""
        # URL remoto -> fetch + encode
        if image.startswith("http://") or image.startswith("https://"):
            import urllib.request
            with urllib.request.urlopen(image, timeout=30) as resp:
                raw = resp.read()
                mime = resp.headers.get("Content-Type", "image/png").split(";")[0]
            b64 = base64.b64encode(raw).decode("ascii")
            return {"inline_data": {"mime_type": mime, "data": b64}}

        # data URI:  data:image/jpeg;base64,XXXX
        if image.startswith("data:"):
            header, _, b64 = image.partition(",")
            mime = "image/png"
            if ":" in header:
                mime = header.split(":", 1)[1].split(";", 1)[0]
            return {"inline_data": {"mime_type": mime, "data": b64}}

        # base64 grezzo -> sniff dei magic bytes per indovinare il MIME
        try:
            head = base64.b64decode(image[:64])
        except Exception:
            head = b""
        if head.startswith(b"\xff\xd8"):
            mime = "image/jpeg"
        elif head.startswith(b"\x89PNG"):
            mime = "image/png"
        elif head.startswith(b"RIFF") and b"WEBP" in head[:16]:
            mime = "image/webp"
        elif head.startswith(b"GIF8"):
            mime = "image/gif"
        else:
            mime = "image/png"
        return {"inline_data": {"mime_type": mime, "data": image}}

    async def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        model: str | None = None,
        image: str | None = None,
        **kwargs,
    ) -> ImageResult:
        key = self.api_key
        if not key:
            raise RuntimeError(
                "Gemini non configurato (manca GOOGLE_API_KEY / GEMINI_API_KEY "
                "o google_gemini in config)"
            )

        model_name = self._normalize_model(model)
        url = f"{self.BASE_URL}/{model_name}:generateContent?key={key}"

        parts: list[dict] = []
        if image:
            parts.append(self._prepare_image_part(image))
        parts.append({"text": prompt})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url, json=payload, headers={"Content-Type": "application/json"}
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Gemini HTTP {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini: nessun candidato nella risposta: {str(data)[:300]}")

        out_b64 = None
        out_mime = "image/png"
        text_response = None

        for part in candidates[0].get("content", {}).get("parts", []):
            if "inlineData" in part:
                out_b64 = part["inlineData"].get("data")
                out_mime = part["inlineData"].get("mimeType", "image/png")
                break
            if "text" in part:
                text_response = part["text"]

        if not out_b64:
            msg = text_response or "Gemini non ha restituito un'immagine"
            raise RuntimeError(msg[:400])

        return ImageResult(
            url=None,
            b64_data=out_b64,
            prompt=prompt,
            model=model_name,
            provider=self.name,
            width=width,
            height=height,
            mime_type=out_mime,
        )


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
        return True

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
    Router image-aware.

    - Se il modello richiesto è Gemini (o ha prefisso google_gemini/), usa Gemini
      in modo esplicito (text-to-image se non c'è `image`, editing se c'è `image`).
    - Se c'è `image` ma il modello non è Gemini, usa Gemini comunque (unico
      provider con editing nel setup attuale).
    - Altrimenti fallback classico: nvidia -> huggingface -> cloudflare -> pollinations.
    """

    def __init__(self, config: Any = None):
        self.config = config
        self.providers: dict[str, ImageProviderBase] = {
            "google_gemini": GeminiImageProvider(config=config),
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

    def _is_gemini_model(self, model: str | None) -> bool:
        if not model:
            return False
        return (
            model.startswith("sinfonia/google_gemini/")
            or model.startswith("google_gemini/")
            or model.startswith("gemini")
        )

    async def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        model: str | None = None,
        image: str | None = None,
        preferred: str | None = None,
    ) -> ImageResult:
        gemini = self.providers["google_gemini"]

        # 1) Modello Gemini esplicitamente richiesto
        if self._is_gemini_model(model):
            if not gemini.is_available:
                raise RuntimeError(
                    f"Modello '{model}' richiesto ma Google Gemini non è configurato "
                    "(imposta GOOGLE_API_KEY o GEMINI_API_KEY in .env)"
                )
            try:
                log.info("image_router.gemini", model=model, has_image=bool(image))
                return await gemini.generate(
                    prompt, width=width, height=height, model=model, image=image
                )
            except RuntimeError as e:
                if image is None and "429" in str(e):
                    log.warning(
                        "image_router.gemini.429_fallback",
                        model=model,
                        reason=str(e)[:120],
                    )
                else:
                    raise

        # 2) Editing richiesto (image in input) -> solo Gemini sa farlo
        if image:
            if not gemini.is_available:
                raise RuntimeError(
                    "Modifica immagine richiesta ma nessun provider di editing "
                    "disponibile. Configura GOOGLE_API_KEY o GEMINI_API_KEY."
                )
            log.info("image_router.gemini.editing", model=model or gemini.DEFAULT_MODEL)
            return await gemini.generate(
                prompt, width=width, height=height, model=model, image=image
            )

        # 3) Fallback classico text-to-image
        order: list[str] = []
        if preferred and preferred in self.providers:
            order.append(preferred)
        for name in ["nvidia", "huggingface", "cloudflare", "pollinations"]:
            if name not in order:
                order.append(name)

        last_error: Exception | None = None
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

        raise RuntimeError(
            f"Nessun provider di immagini disponibile. Ultimo errore: {last_error}"
        )


if __name__ == "__main__":
    async def _test():
        router = ImageRouter()
        print(f"Provider disponibili: {router.available_providers()}")
        if router.available_providers():
            result = await router.generate("un leone maestoso nella savana al tramonto")
            print(f"Provider: {result.provider}")
            print(f"URL: {result.url[:100] if result.url else None}")

    asyncio.run(_test())