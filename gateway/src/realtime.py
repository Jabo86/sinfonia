"""
Sinfonia — Real-time Context

Fornisce al gateway dati in tempo reale: data/ora corrente, meteo.
Nessuna API key richiesta (wttr.in).
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx
import structlog

log = structlog.get_logger()

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
GIORNI = [
    "lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica",
]


def build_system_prompt() -> str:
    """Costruisce il system prompt con data/ora correnti (aggiornate ad ogni chiamata)."""
    now = datetime.now()
    data_str = f"{GIORNI[now.weekday()]} {now.day} {MESI[now.month - 1]} {now.year}"
    ora_str = now.strftime("%H:%M")

    return f"""ISTRUZIONI OBBLIGATORIE:

1. Rispondi SEMPRE in Markdown (titoli ##, grassetti **, elenchi -).

2. Usa SEMPRE LaTeX per le formule matematiche. USA SOLO QUESTI DELIMITATORI:
   - Formule inline: $formula$
   - Formule in blocco: $$formula$$
   NON usare parentesi quadre o tonde per il LaTeX.

3. Per problemi di GEOMETRIA o FIGURE, disegna la figura con SVG inline.

4. Struttura: ## Dati, ## Svolgimento, ## Risultato finale.

CONTESTO IN TEMPO REALE (fornito dal sistema, usalo come verita):
- Data corrente: {data_str}
- Ora corrente: {ora_str}
- Se ricevi un messaggio di sistema con dati meteo, usali direttamente.
- NON dire "non ho accesso a dati in tempo reale": il sistema te li fornisce.
- Se l'utente chiede la data o l'ora, rispondi con i valori sopra.
- Se l'utente chiede il meteo e ricevi i dati, riportali direttamente.
"""


WEATHER_KEYWORDS = [
    "meteo", "temperatura", "che tempo", "clima", "piove", "sole",
    "caldo", "freddo", "gradi", "pioggia", "neve", "vento", "umidita",
    "umidità", "previsioni",
]

STOPWORDS = {
    "genere", "questo", "quel", "modo", "generale", "particolare",
    "italia", "europa", "citta", "città", "paese", "zona", "regione",
    "oggi", "domani", "ieri", "adesso", "ora",
}


def detect_weather_city(message: str) -> str | None:
    """Rileva se la domanda riguarda il meteo e restituisce la citta."""
    msg = message.lower()
    if not any(k in msg for k in WEATHER_KEYWORDS):
        return None

    # Pattern con maiuscola: "a Venezia", "di Milano"
    m = re.search(
        r'\b(?:a|di|per|in|da|su)\s+([A-Z][a-zà-ù]+(?:\s+[A-Z][a-zà-ù]+)?)',
        message,
    )
    if m:
        city = m.group(1)
        if city.lower() not in STOPWORDS:
            return city

    # Pattern minuscolo: "a venezia"
    m = re.search(
        r'\b(?:a|di|per|in|da|su)\s+([a-zà-ù]{3,}(?:\s+[a-zà-ù]+)?)',
        msg,
    )
    if m:
        city = m.group(1).strip()
        first = city.split()[0]
        if first not in STOPWORDS:
            return city.title()

    return None


async def get_weather(city: str) -> dict:
    """Recupera il meteo corrente da wttr.in (gratis, no API key)."""
    url = f"https://wttr.in/{city}?format=j1&lang=it"
    headers = {"User-Agent": "curl/8.0"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    cc = data["current_condition"][0]

    # Descrizione: prova lang_it (italiano), poi weatherDesc (inglese)
    desc = cc.get("lang_it") or cc.get("weatherDesc", [{}])[0].get("value", "?")

    return {
        "city": city,
        "temp_C": cc.get("temp_C", "?"),
        "feels_like_C": cc.get("FeelsLikeC", "?"),
        "description": desc,
        "humidity": cc.get("humidity", "?"),
        "wind_kmph": cc.get("windspeedKmph", "?"),
        "wind_dir": cc.get("winddir16Point", "?"),
        "uv_index": cc.get("uvIndex", "?"),
    }


if __name__ == "__main__":
    import asyncio

    print("=== Test system prompt ===")
    prompt = build_system_prompt()
    # Mostra solo la parte finale con data/ora
    print(prompt[-400:])
    print()

    print("=== Test rilevamento meteo ===")
    tests = [
        "Che giorno e oggi e che temperatura c'e a Venezia?",
        "Che meteo fa a Milano?",
        "Spiega la fotosintesi",
        "Quanti gradi ci sono a Roma adesso?",
        "Che tempo fa a New York?",
    ]
    for t in tests:
        print(f"  {t!r} -> {detect_weather_city(t)}")

    print()
    print("=== Test meteo reale (Venezia) ===")
    w = asyncio.run(get_weather("Venezia"))
    for k, v in w.items():
        print(f"  {k}: {v}")

def build_voice_prompt() -> str:
    """System prompt per modalita vocale: risposte brevi, dirette, senza markdown."""
    now = datetime.now()
    data_str = f"{GIORNI[now.weekday()]} {now.day} {MESI[now.month - 1]} {now.year}"
    ora_str = now.strftime("%H:%M")

    return f"""Sei un assistente vocale. Le tue risposte vengono LETTE AD ALTA VOCE.

REGOLE FONDAMENTALI:
1. Rispondi in MASSIMO 1-3 frasi brevi. Sii conciso e diretto.
2. NON usare markdown (no ##, no **, no elenchi, no backtick).
3. NON usare LaTeX o simboli matematici. Leggi i numeri normalmente.
4. NON dire "Dati", "Svolgimento", "Risultato" o altre intestazioni.
5. Vai dritto al punto come in una conversazione tra amici.
6. Se ti chiedono la data, di' solo "Oggi e' [giorno] [numero] [mese] [anno]".
7. Se ti chiedono l'ora, di' solo l'ora.
8. Se ti chiedono il meteo, di' temperatura e condizioni in una frase.

CONTESTO IN TEMPO REALE:
- Data: {data_str}
- Ora: {ora_str}

Rispondi SOLO con il testo da leggere ad alta voce."""
