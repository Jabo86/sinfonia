cat << 'README_EOF' > ~/sinfonia/README.md
# 🎼 Sinfonia

> **L'orchestrazione etica dell'intelligenza artificiale.**
> Adaptive AI Orchestration — Free-First, Paid-Ready.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![BYOK](https://img.shields.io/badge/BYOK-Bring_Your_Own_Key-green.svg)](#)
[![ToS-Compliant](https://img.shields.io/badge/ToS-Compliant-blue.svg)](#)
[![Status: Active Development](https://img.shields.io/badge/Status-Active_Development-orange.svg)](#)

Sinfonia è un orchestratore adattivo di intelligenze artificiali che coordina
molteplici modelli (gratuiti e a pagamento) rispettando rigorosamente i
Termini di Servizio di ciascun provider.

Non aggira limiti. Non poola chiavi. Non nasconde costi.
Orchestra, con trasparenza radicale.

---

## ✨ Caratteristiche

### 🎯 Orchestrazione intelligente
- **Free-First, Paid-Ready**: usa i provider gratuiti per default, integra
  quelli a pagamento quando e se lo desideri.
- **Multi-provider**: 11 provider gratuiti + 3 a pagamento configurati di
  default (Groq, Gemini, Cerebras, OpenRouter, Mistral, GitHub Models,
  SambaNova, Cloudflare, NVIDIA, GLM, Kimi, OpenAI, Anthropic, Vertex AI).
- **Routing quota-aware**: sceglie automaticamente il provider con più quota
  residua, con fallback su 429 e circuit breaker per isolare i provider guasti.
- **Continuità conversazione**: se un provider esaurisce la quota, la
  conversazione continua su un altro senza perdere il contesto.

### 🎨 Modalità di risposta
- **Single** (default): una sola AI risponde, scelta dal router.
- **Ensemble**: 3 AI rispondono in parallelo, un giudice locale (via Ollama)
  sintetizza la risposta migliore. Zero consumo extra di quota API per il giudice.
- **Frugale**: quando le quote sono basse, riduce automaticamente la complessità.
- **Fallback Locale**: quando tutte le quote free sono esaurite, propone un
  modello locale.

### 🌐 Multimodalità
- **Testo**: chat con Markdown, LaTeX (KaTeX), syntax highlighting.
- **Codice**: blocchi con copia, evidenziazione linguaggio.
- **Figure geometriche**: SVG inline generati dal modello.
- **Diagrammi**: Mermaid rendering (flowchart, sequence, ecc.).
- **Immagini**: generazione multi-provider (Pollinations, NVIDIA, HuggingFace,
  Cloudflare).
- **Video**: generazione con InferencePort.
- **Musica**: generazione con Tunova (Suno v5.5).
- **Traduzione**: 150 lingue via Index-Translate.

### 🧠 Contesto in tempo reale
- **Data e ora correnti** iniettate dinamicamente ad ogni richiesta.
- **Meteo reale** via wttr.in (gratis, no API key) quando la domanda lo richiede.
- **Rilevamento automatico** della città dalla domanda.

### 🔍 Trasparenza radicale
- **Dashboard crediti** in tempo reale nella UI.
- **Badge provider** su ogni risposta (chi ha risposto, token, tempo).
- **CLI `sinfonia`**: comandi `status`, `usage`, `providers`, `models`, `update`.
- **Endpoint API**: `/v1/credits`, `/v1/quota`, `/v1/usage`, `/v1/estimate`.

### 🛡️ Auto-guarigione
- **Circuit breaker** per isolare i provider con errori ripetuti.
- **Self-healer** che diagnostica gli errori (rate limit, auth, model not found).
- **Auto-scoperta modelli**: ogni 24h interroga `/v1/models` dei provider per
  aggiornare il catalogo.

### 🎨 UI moderna
- **Design glassmorphism** dark/light mode.
- **Sidebar collassabile** con ricerca conversazioni.
- **Streaming thinking indicator** durante la generazione.
- **Toast notifications** per eventi e errori.
- **Shortcuts**: ⌘K nuova chat, Invio invia, Shift+Invio va a capo.

### 🚀 Avvio automatico
- Servizio **launchd** su macOS che avvia Sinfonia al login.
- Log in `sinfonia.log` e `sinfonia.err.log`.

---

## 🔒 Principi Non Negoziabili

1. **BYOK** — L'utente fornisce le proprie chiavi. Sinfonia non le condivide,
   non le rivende, non le poola.
2. **Rispetto dei limiti dichiarati** — Il sistema non supera mai un rate limit.
3. **Nessun pooling multi-account** — Una chiave per provider per utente.
4. **Nessuna funzionalità di stealth o anti-ban** — Sinfonia rifiuta
   esplicitamente di implementare TLS fingerprinting, header spoofing o simili.
5. **Trasparenza radicale** — L'utente vede sempre, prima di ogni operazione,
   quanto consumerà in quote free e in denaro.

Qualsiasi contributo che violi uno di questi principi verrà rifiutato.

---

## 🚀 Quick Start

### 1. Clona e installa

```bash
git clone https://github.com/Jabo86/sinfonia.git
cd sinfonia
python3 -m venv venv
source venv/bin/activate
pip install -r gateway/requirements.txt
