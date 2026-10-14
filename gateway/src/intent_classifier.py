"""
Sinfonia — Intent Classifier

Riconosce l'intento dell'utente (testo, immagine, video, musica, traduzione)
in base a parole chiave. In futuro, useremo un LLM locale per classificazioni
piu' accurate.
"""

from __future__ import annotations

from enum import Enum

import structlog

log = structlog.get_logger()


class Intent(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    MUSIC = "music"
    TRANSLATION = "translation"


# Parole chiave per ogni intento (case-insensitive)
KEYWORDS = {
    Intent.IMAGE: [
        "disegna", "disegnami", "disegnare",
        "immagine", "immagini", "figura", "illustra", "illustrami",
        "foto", "fotografia", "rendering", "dipinto",
        "genera un'immagine", "crea un'immagine", "creami un'immagine",
        "crea un'immagine di", "genera immagine di",
        "crea ", "creami ", "genera ", "generami ",
        "draw", "image", "picture", "illustration", "render",
    ],
    Intent.VIDEO: [
        "video", "animazione", "clip", "filmato", "film", "animato",
        "genera un video", "crea un video", "creami un video",
        "movie", "animation",
    ],
    Intent.MUSIC: [
        "canzone", "musica", "melodia", "brano", "traccia", "componi",
        "componimi", "genera una canzone", "crea una canzone",
        "canzone jazz", "canzone rock", "canzone pop",
        "song", "music", "track", "beat", "strumentale",
    ],
    Intent.TRANSLATION: [
        "traduci", "traduzione", "translate", "translation",
        "in inglese", "in francese", "in spagnolo", "in tedesco",
        "in cinese", "in giapponese", "in arabo", "in russo",
    ],
}


def classify(message: str) -> Intent:
    """
    Classifica l'intento di un messaggio.

    Args:
        message: il testo del messaggio dell'utente

    Returns:
        Intent corrispondente
    """
    msg = message.lower().strip()

    # Controlla ogni intento in ordine di priorita'
    for intent in [Intent.VIDEO, Intent.MUSIC, Intent.IMAGE, Intent.TRANSLATION]:
        for kw in KEYWORDS[intent]:
            if kw in msg:
                log.info("intent.classified", intent=intent.value, keyword=kw)
                return intent

    return Intent.TEXT


def extract_prompt(message: str, intent: Intent) -> str:
    """
    Estrae il prompt "pulito" dal messaggio, rimuovendo le parole chiave.
    """
    msg = message.strip()

    # Rimuovi prefissi comuni
    prefixes = [
        "disegna ", "genera un'immagine di ", "crea un'immagine di ",
        "genera un video di ", "crea un video di ",
        "componi ", "genera una canzone ", "crea una canzone ",
        "traduci ", "translate ",
    ]
    for p in prefixes:
        if msg.lower().startswith(p):
            return msg[len(p):].strip()

    return msg


if __name__ == "__main__":
    tests = [
        "Disegna un leone nella savana",
        "Crea un video di un tramonto",
        "Componi una canzone jazz",
        "Traduci in inglese: ciao mondo",
        "Spiega la fotosintesi",
    ]
    for t in tests:
        intent = classify(t)
        prompt = extract_prompt(t, intent)
        print(f"{t!r:50} -> {intent.value:15} -> {prompt!r}")
