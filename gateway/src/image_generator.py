"""
Sinfonia — Image Generator

Genera immagini con Pollinations.ai (Flux).
Nessuna API key richiesta.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

import structlog

log = structlog.get_logger()


@dataclass
class ImageResult:
    url: str
    prompt: str
    width: int
    height: int
    model: str
    provider: str = "pollinations"

    def to_dict(self) -> dict:
        return {
            "type": "image",
            "url": self.url,
            "prompt": self.prompt,
            "width": self.width,
            "height": self.height,
            "model": self.model,
            "provider": self.provider,
        }


class ImageGenerator:
    """
    Genera immagini con Pollinations.ai.
    Nessuna API key richiesta (tier anonimo).
    """

    BASE_URL = "https://image.pollinations.ai/prompt"

    def __init__(self, model: str = "flux"):
        self.model = model

    async def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        model: str | None = None,
        nologo: bool = True,
    ) -> ImageResult:
        """
        Genera un'immagine da un prompt.

        Args:
            prompt: descrizione dell'immagine
            width: larghezza in pixel
            height: altezza in pixel
            model: modello (flux, turbo, stable-diffusion, kontext)
            nologo: rimuove il logo Pollinations (se registrato)

        Returns:
            ImageResult con l'URL dell'immagine
        """
        model = model or self.model
        encoded_prompt = urllib.parse.quote(prompt)

        params = {
            "width": str(width),
            "height": str(height),
            "model": model,
            "nologo": "true" if nologo else "false",
            "seed": str(hash(prompt) % 1000000),
        }
        query = urllib.parse.urlencode(params)
        url = f"{self.BASE_URL}/{encoded_prompt}?{query}"

        log.info("image.generate", prompt=prompt[:50], model=model, size=f"{width}x{height}")

        return ImageResult(
            url=url,
            prompt=prompt,
            width=width,
            height=height,
            model=model,
        )


# Test rapido
if __name__ == "__main__":
    import asyncio

    async def test():
        gen = ImageGenerator()
        result = await gen.generate("un leone maestoso nella savana al tramonto")
        print(f"URL: {result.url}")

    asyncio.run(test())
