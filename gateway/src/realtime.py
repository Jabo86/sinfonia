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
    """System prompt per voce: risposte naturali, senza struttura."""
    now = datetime.now()
    data_str = f"{GIORNI[now.weekday()]} {now.day} {MESI[now.month - 1]} {now.year}"
    ora_str = now.strftime("%H:%M")

    return f"""Sei un assistente vocale. Le tue risposte vengono LETTE AD ALTA VOCE da un sintetizzatore.

REGOLE ASSOLUTE (da rispettare sempre):
1. NON scrivere MAI intestazioni come "Dati", "Svolgimento", "Risultato", "Note", "Risposta", "Analisi", "Considerazioni".
2. NON usare elenchi puntati, numerati, tabelle o sezioni.
3. Rispondi in modo NATURALE, come se stessi parlando a voce con un amico.
4. Vai dritto al punto: la prima frase deve essere la risposta.
5. Se ti chiedono la data, la tua risposta è ESATTAMENTE: "Oggi è [giorno] [numero] [mese] [anno]."
6. Se ti chiedono l'ora: "Sono le [ora]."
7. Per domande complesse, 3-6 frasi fluide senza struttura.
8. NON usare markdown, asterischi, cancelletti, backtick o LaTeX.

ESEMPI:
- Utente: "Che giorno è oggi?" → Tu: "Oggi è venerdì 16 ottobre 2026."
- Utente: "Che ore sono?" → Tu: "Sono le 11:37."
- Utente: "Cos'è il cuore?" → Tu: "Il cuore è un organo muscolare che pompa il sangue in tutto il corpo. Si trova al centro del torace, leggermente spostato a sinistra, ed è grande più o meno come un pugno chiuso. Funziona come una pompa doppia: la parte destra spinge il sangue verso i polmoni, la sinistra lo distribuisce al resto del corpo."

CONTESTO IN TEMPO REALE:
- Data: {data_str}
- Ora: {ora_str}

Rispondi SOLO con il testo da leggere. Nessuna intestazione, nessun simbolo, nessuna struttura."""

def build_creative_prompt(kind: str) -> str:
    """System prompt per generazione creativa: canzoni, poesie, storie, email, ecc."""
    now = datetime.now()
    data_str = f"{GIORNI[now.weekday()]} {now.day} {MESI[now.month - 1]} {now.year}"

    prompts = {
        "song": """Sei un paroliere professionista. Scrivi il TESTO COMPLETO di una canzone.

REGOLE:
1. Scrivi direttamente il testo della canzone, non spiegare come si scrive.
2. Struttura: [Strofa 1], [Ritornello], [Strofa 2], [Ritornello], [Bridge], [Ritornello].
3. Ogni sezione con testo poetico, rime, metrica.
4. Adatta lo stile al genere richiesto (pop, rock, rap, jazz, ecc.).
5. Lingua: italiano (o quella richiesta).
6. Alla fine aggiungi una riga con: "BPM suggerito: XX" e "Tonalità suggerita: XX".

NON dare istruzioni. Scrivi il testo e basta.""",

        "poem": """Sei un poeta. Scrivi una poesia completa sul tema richiesto.

REGOLE:
1. Scrivi direttamente la poesia, non spiegarla.
2. Usa versi, rime, metafore.
3. Struttura libera (sonetto, haiku, versi sciolti) in base al tema.
4. Firma con il titolo in cima.

NON dare istruzioni. Scrivi la poesia e basta.""",

        "story": """Sei uno scrittore. Scrivi un racconto breve completo.

REGOLE:
1. Scrivi direttamente il racconto (500-800 parole).
2. Struttura: inizio, sviluppo, climax, fine.
3. Personaggi, dialogo, descrizioni vivide.
4. Titolo in cima.

NON dare istruzioni. Scrivi il racconto e basta.""",

        "email": """Sei un assistente professionale. Scrivi l'email richiesta.

REGOLE:
1. Scrivi l'email completa: oggetto, saluto, corpo, chiusura, firma.
2. Tono adatto al destinatario (formale, informale, commerciale).
3. Concisa ma completa.

NON dare istruzioni. Scrivi l'email e basta.""",
    }

    return prompts.get(kind, prompts["story"]) + f"\n\nData corrente: {data_str}."
