"""
Sinfonia — Real-time Context
Data/ora correnti, meteo (wttr.in), prompt dinamici.
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


def _now_strings():
    now = datetime.now()
    data_str = f"{GIORNI[now.weekday()]} {now.day} {MESI[now.month - 1]} {now.year}"
    ora_str = now.strftime("%H:%M")
    return now, data_str, ora_str


# === SYSTEM PROMPTS =========================================================

def build_system_prompt() -> str:
    """System prompt standard (chat scritta)."""
    now, data_str, ora_str = _now_strings()

    return f"""ISTRUZIONI OBBLIGATORIE:

1. Rispondi SEMPRE in Markdown (titoli ##, grassetti **, elenchi -).

2. Usa SEMPRE LaTeX per le formule matematiche. USA SOLO QUESTI DELIMITATORI:
   - Formule inline: $formula$
   - Formule in blocco: $$formula$$
   NON usare parentesi quadre o tonde per il LaTeX.

3. Per problemi di GEOMETRIA o FIGURE, disegna la figura con SVG inline.

4. Struttura la risposta cosi: ## Dati, ## Svolgimento, ## Risultato finale.

=================================================================
DATI DI SISTEMA (VERITA' ASSOLUTA — NON IGNORARE):
=================================================================
- Oggi e': {data_str}
- Ora corrente: {ora_str}
=================================================================

REGOLE SULLA DATA:
- Se l'utente chiede la data, DEVI rispondere ESATTAMENTE: "Oggi e' {data_str}."
- NON dire "non ho accesso alla data corrente": ce l'hai, e' scritta sopra.
- NON inventare il giorno: e' {GIORNI[now.weekday()]}.
- Se ricevi un messaggio di sistema con dati meteo, usali direttamente.
"""


def build_voice_prompt() -> str:
    """System prompt per voce (brevi risposte)."""
    now, data_str, ora_str = _now_strings()

    return f"""Sei un assistente vocale esperto. Le tue risposte vengono LETTE AD ALTA VOCE.

REGOLE:
1. Rispondi in MASSIMO 2-3 frasi brevi. Sii conciso e diretto.
2. NON usare markdown (no ##, no **, no elenchi).
3. NON usare LaTeX o simboli matematici.
4. NON dire "Dati", "Svolgimento", "Risultato finale".
5. Parla come in una conversazione tra amici.

CONTESTO IN TEMPO REALE:
- Data: {data_str}
- Ora: {ora_str}

Rispondi SOLO con il testo da leggere. Breve, naturale, diretto."""


def build_voice_prompt_with_profession(profession_name: str, profession_id: str) -> str:
    """System prompt voce breve con identita' del profilo."""
    now, data_str, ora_str = _now_strings()

    return f"""Sei {profession_name}, assistente vocale esperto (profilo: {profession_id}).

MODALITA' VOCALE — REGOLE:
1. Rispondi in MASSIMO 2-3 frasi brevi.
2. NON usare markdown, LaTeX, elenchi o tabelle.
3. NON dire intestazioni come "Dati", "Analisi", "Risultato".
4. Se fuori tema, NON segnalarlo in voce: rispondi breve.
5. Se l'utente vuole dettagli, te lo chiedera'.

CONTESTO:
- Data: {data_str}
- Ora: {ora_str}

Rispondi SOLO con il testo da leggere. Breve, naturale."""


def build_creative_prompt(kind: str) -> str:
    """System prompt per generazione creativa: canzoni, poesie, storie, email."""
    now, data_str, ora_str = _now_strings()

    prompts = {
        "song": """Sei un paroliere professionista. Scrivi il TESTO COMPLETO di una canzone.

REGOLE:
1. Scrivi direttamente il testo, non spiegare come si scrive.
2. Struttura: [Strofa 1], [Ritornello], [Strofa 2], [Ritornello], [Bridge], [Ritornello].
3. Ogni sezione con testo poetico, rime, metrica.
4. Adatta lo stile al genere richiesto (pop, rock, rap, jazz, ecc.).
5. Lingua: italiano (o quella richiesta).
6. Alla fine aggiungi una riga: "BPM suggerito: XX" e "Tonalita suggerita: XX".

NON dare istruzioni. Scrivi il testo e basta.""",

        "poem": """Sei un poeta. Scrivi una poesia completa sul tema richiesto.

REGOLE:
1. Scrivi direttamente la poesia, non spiegarla.
2. Usa versi, rime, metafore.
3. Titolo in cima.

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

NON dare istruzioni. Scrivi l'email e basta.""",
    }

    return prompts.get(kind, prompts["story"]) + f"\n\nData corrente: {data_str}."


# === METEO ==================================================================

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

    # Pattern con maiuscola
    m = re.search(
        r'\b(?:a|di|per|in|da|su)\s+([A-Z][a-zà-ù]+(?:\s+[A-Z][a-zà-ù]+)?)',
        message,
    )
    if m:
        city = m.group(1)
        if city.lower() not in STOPWORDS:
            return city

    # Pattern minuscolo
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
    """Recupera il meteo corrente da wttr.in."""
    url = f"https://wttr.in/{city}?format=j1&lang=it"
    headers = {"User-Agent": "curl/8.0"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    cc = data["current_condition"][0]
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


# === TEST ===================================================================

if __name__ == "__main__":
    print("=== System prompt ===")
    print(build_system_prompt()[:400])
    print()
    print("=== Rilevamento meteo ===")
    tests = [
        "che tempo fa a Venezia?",
        "che giorno e oggi?",
    ]
    for t in tests:
        print(f"  {t!r} -> {detect_weather_city(t)}")
