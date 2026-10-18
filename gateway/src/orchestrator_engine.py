#!/usr/bin/env python3
"""
Orchestratore minimale multi-agente per Ollama.

Pipeline: Planner -> Developer -> Tester -> Bug-finder -> Reviewer
Salva stato in .orchestrator/state.json (resumabile).
Log in .orchestrator/log.txt (append).

Uso:
    python3 orchestrator.py ~/progetti/mio-progetto
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

OLLAMA = "http://localhost:11434"
MODEL = "qwen2.5-coder:7b-32k"
MAX_FILE_RETRIES = 3
MAX_FIX_ATTEMPTS = 2
TIMEOUT = 600.0


def llm(prompt: str, system: str = "Sei un assistente esperto di coding.") -> str:
    """Chiama Ollama e restituisce il testo della risposta."""
    r = httpx.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 32768},
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def log(state: dict, msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    state["log_path"].parent.mkdir(exist_ok=True)
    with open(state["log_path"], "a") as f:
        f.write(line + "\n")


def save_state(state: dict) -> None:
    state["state_path"].write_text(json.dumps(
        {k: v for k, v in state.items() if not k.endswith("_path")},
        indent=2, default=str,
    ))


def parse_json_block(text: str) -> dict | list | None:
    """Estrae il primo blocco JSON dalla risposta del LLM."""
    start = text.find("{")
    if start < 0:
        start = text.find("[")
        if start < 0:
            return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


# ---------- Agenti ----------

def planner(state: dict) -> list[dict]:
    """Legge REQUIREMENTS.md e restituisce lista di file da creare."""
    log(state, "PLANNER: leggo REQUIREMENTS.md")
    req = state["requirements"]
    prompt = f"""Leggi i requisiti e produci un piano JSON con la lista dei file da creare.

REQUISITI:
{req}

Rispondi SOLO con JSON valido, formato:
{{
  "files": [
    {{
      "path": "src/calculator.py",
      "purpose": "Implementa add, sub, mul, div con errori chiari",
      "depends_on": []
    }},
    {{
      "path": "tests/test_calculator.py",
      "purpose": "Test unitari per ogni operazione",
      "depends_on": ["src/calculator.py"]
    }}
  ]
}}

Nessun testo extra. Solo il JSON.
"""
    resp = llm(prompt, system="Sei un architetto software. Produci solo JSON.")
    plan = parse_json_block(resp)
    if not plan or "files" not in plan:
        log(state, f"PLANNER: risposta non valida, uso piano di fallback")
        plan = {"files": [
            {"path": "src/calculator.py", "purpose": "Implementa add, sub, mul, div", "depends_on": []},
            {"path": "tests/test_calculator.py", "purpose": "Test unitari", "depends_on": ["src/calculator.py"]},
            {"path": "src/main.py", "purpose": "CLI entry point", "depends_on": ["src/calculator.py"]},
        ]}
    log(state, f"PLANNER: {len(plan['files'])} file da creare")
    return plan["files"]


def developer(state: dict, file_spec: dict, project_dir: Path) -> bool:
    """Chiede al modello di scrivere un file e lo salva su disco."""
    path = project_dir / file_spec["path"]
    path.parent.mkdir(parents=True, exist_ok=True)

    # Contesto: file già esistenti da cui dipende
    context = ""
    for dep in file_spec.get("depends_on", []):
        dep_path = project_dir / dep
        if dep_path.exists():
            context += f"\n--- CONTENUTO DI {dep} ---\n{dep_path.read_text()}\n"

    log(state, f"DEVELOPER: scrivo {file_spec['path']}")
    prompt = f"""Scrivi il file `{file_spec['path']}`.

SCOPO: {file_spec['purpose']}
{context}

REQUISITI ORIGINALI:
{state['requirements'][:2000]}

Rispondi SOLO con il contenuto del file, senza spiegazioni, senza markdown fences.
Inizia direttamente con `import` o `def` o `class` o `from`.
"""
    content = llm(prompt, system="Sei uno sviluppatore Python senior. Scrivi codice pulito e testabile.")
    # Rimuovi eventuali markdown fences
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    path.write_text(content + "\n")
    log(state, f"DEVELOPER: {file_spec['path']} scritto ({len(content)} byte)")
    return True


def tester(state: dict, project_dir: Path) -> tuple[bool, str]:
    """Esegue i test. Restituisce (pass, output)."""
    log(state, "TESTER: eseguo unittest")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "tests/", "-v"],
            cwd=project_dir,
            capture_output=True, text=True, timeout=60,
        )
        out = (r.stdout + r.stderr)[-3000:]
        ok = r.returncode == 0
        log(state, f"TESTER: {'PASS' if ok else 'FAIL'} (output {len(out)} chars)")
        return ok, out
    except subprocess.TimeoutExpired:
        log(state, "TESTER: TIMEOUT")
        return False, "Test timeout dopo 60 secondi"


def bug_finder(state: dict, project_dir: Path, test_output: str) -> bool:
    """Chiede al modello di correggere i file che causano fallimenti."""
    log(state, "BUG-FINDER: analizzo i fallimenti")

    # Trova i file colpevoli (quelli con errori menzionati)
    files_to_check = []
    for f in (project_dir / "src").glob("*.py"):
        files_to_check.append(f)
    for f in (project_dir / "tests").glob("*.py"):
        files_to_check.append(f)

    if not files_to_check:
        log(state, "BUG-FINDER: nessun file da correggere")
        return False

    # Chiede una diagnosi
    files_dump = ""
    for f in files_to_check:
        files_dump += f"\n--- {f.relative_to(project_dir)} ---\n{f.read_text()}\n"

    prompt = f"""I test falliscono. Output:

{test_output}

File del progetto:
{files_dump}

Identifica QUALE file è sbagliato e riscrivirlo.
Rispondi SOLO con JSON:
{{
  "fixes": [
    {{"path": "src/calculator.py", "new_content": "..."}}
  ]
}}
"""
    resp = llm(prompt, system="Sei un debugger esperto. Rispondi solo JSON.")
    fixes = parse_json_block(resp)
    if not fixes or "fixes" not in fixes:
        log(state, "BUG-FINDER: nessun fix proposto")
        return False

    for fix in fixes["fixes"]:
        p = project_dir / fix["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        content = fix["new_content"].strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        p.write_text(content + "\n")
        log(state, f"BUG-FINDER: corretto {fix['path']}")

    return True


def reviewer(state: dict, project_dir: Path) -> str:
    """Revisione finale."""
    log(state, "REVIEWER: revisione finale")
    files_dump = ""
    for f in project_dir.rglob("*.py"):
        if ".orchestrator" in str(f) or "__pycache__" in str(f):
            continue
        files_dump += f"\n--- {f.relative_to(project_dir)} ---\n{f.read_text()}\n"

    prompt = f"""Rivedi questo progetto rispetto ai requisiti.

REQUISITI:
{state['requirements']}

FILE:
{files_dump[:6000]}

Rispondi con una riga sola:
- "APPROVED" se il progetto è completo e corretto
- "REJECTED: <motivo>" se manca qualcosa
"""
    resp = llm(prompt, system="Sei un code reviewer severo.").strip()
    verdict = resp.split("\n")[0]
    log(state, f"REVIEWER: {verdict[:120]}")
    return verdict


# ---------- Main ----------

def main():
    project_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    orch_dir = project_dir / ".orchestrator"
    orch_dir.mkdir(exist_ok=True)

    req_file = project_dir / "REQUIREMENTS.md"
    if not req_file.exists():
        print(f"ERRORE: {req_file} non esiste")
        sys.exit(1)

    state = {
        "requirements": req_file.read_text(),
        "state_path": orch_dir / "state.json",
        "log_path": orch_dir / "log.txt",
        "project_dir": str(project_dir),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "phase": "start",
    }

    # Resume: se esiste state.json, riprendi da dove era
    if state["state_path"].exists():
        try:
            prev = json.loads(state["state_path"].read_text())
            if prev.get("project_dir") == str(project_dir) and prev.get("phase") in ("developing", "testing"):
                log(state, f"RESUME da fase {prev['phase']}")
                state.update(prev)
        except Exception:
            pass

    log(state, f"=== START progetto {project_dir} ===")

    # 1. Planner
    if state["phase"] == "start":
        files = planner(state)
        state["files"] = files
        state["phase"] = "developing"
        save_state(state)
    else:
        files = state.get("files", [])
        log(state, f"RESUME: {len(files)} file nel piano")

    # 2. Developer per ogni file
    for spec in files:
        target = project_dir / spec["path"]
        if target.exists() and state["phase"] != "developing":
            log(state, f"SKIP {spec['path']} (esiste già)")
            continue
        for attempt in range(1, MAX_FILE_RETRIES + 1):
            log(state, f"DEVELOPER {spec['path']} tentativo {attempt}/{MAX_FILE_RETRIES}")
            try:
                developer(state, spec, project_dir)
                break
            except Exception as e:
                log(state, f"DEVELOPER errore: {e}")

    state["phase"] = "testing"
    save_state(state)

    # 3. Tester + Bug-finder loop
    for fix_attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        ok, out = tester(state, project_dir)
        if ok:
            log(state, "TESTER: tutti i test passano")
            break
        if fix_attempt == MAX_FIX_ATTEMPTS:
            log(state, f"BUG-FINDER: resa dopo {MAX_FIX_ATTEMPTS} tentativi")
            break
        log(state, f"BUG-FINDER: tentativo {fix_attempt}/{MAX_FIX_ATTEMPTS}")
        try:
            if not bug_finder(state, project_dir, out):
                log(state, "BUG-FINDER: nessun fix, mi arrendo")
                break
        except Exception as e:
            log(state, f"BUG-FINDER errore: {e}")
            break

    # 4. Reviewer
    state["phase"] = "reviewing"
    save_state(state)
    verdict = reviewer(state, project_dir)

    state["phase"] = "done"
    state["verdict"] = verdict
    save_state(state)
    log(state, f"=== FINE: {verdict[:200]} ===")
    log(state, f"File prodotti: {[str(p.relative_to(project_dir)) for p in project_dir.rglob('*.py') if '.orchestrator' not in str(p) and '__pycache__' not in str(p)]}")


if __name__ == "__main__":
    main()
