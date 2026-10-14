"""
Sinfonia — Translator

Traduzione con Index-Translate (Bilibili), 150 lingue, gratis.
API OpenAI-compatible: https://index-translate.bilibili.com/v1
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()


@dataclass
class TranslationResult:
    translated_text: str
    source_lang: str
    target_lang: str
    provider: str = "index-translate"

    def to_dict(self) -> dict:
        return {
            "type": "translation",
            "translated_text": self.translated_text,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "provider": self.provider,
        }


class Translator:
    """
    Traduce testi con Index-Translate (Bilibili).
    Supporta 150 lingue.
    """

    BASE_URL = "https://index-translate.bilibili.com/v1"

    async def translate(
        self,
        text: str,
        target_lang: str = "en",
        source_lang: str | None = None,
    ) -> TranslationResult:
        """
        Traduce un testo.

        Args:
            text: testo da tradurre
            target_lang: lingua di destinazione (codice ISO 639-1)
            source_lang: lingua di partenza (auto-detect se None)

        Returns:
            TranslationResult
        """
        prompt = f"Translate the following text to {target_lang}:\n\n{text}"

        payload = {
            "model": "index-translate-35b-a3b",
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }

        log.info("translation.request", target=target_lang, length=len(text))

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/chat/completions", json=payload
            )
            resp.raise_for_status()
            data = resp.json()

        translated = data["choices"][0]["message"]["content"]

        return TranslationResult(
            translated_text=translated,
            source_lang=source_lang or "auto",
            target_lang=target_lang,
        )


# Test rapido
if __name__ == "__main__":
    import asyncio

    async def test():
        t = Translator()
        result = await t.translate("Ciao, come stai?", target_lang="en")
        print(f"Tradotto: {result.translated_text}")

    asyncio.run(test())
