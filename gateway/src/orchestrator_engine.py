import json, subprocess, sys, time
from pathlib import Path
import httpx

OLLAMA = "http://localhost:11434"
MODEL = "qwen2.5-coder:7b-32k"
MAX_FIX_ATTEMPTS = 2
TIMEOUT = 600.0

LANG_PROFILES = {
    "python": {
        "ext": ".py",
        "system": "Sei uno sviluppatore Python senior. Scrivi codice pulito, testabile, con type hints quando utile.",
        "test_cmd": ["python3", "-m", "unittest", "discover", "tests/", "-v"],
        "test_hint": "I test sono in tests/ e si eseguono con python3 -m unittest discover tests/ -v.",
        "src_dir": "src", "test_dir": "tests",
    },
    "rust": {
        "ext": ".rs",
        "system": "Sei uno sviluppatore Rust senior. Scrivi codice idiomatico, senza unsafe non necessario.",
        "test_cmd": ["cargo", "test", "--quiet"],
        "test_hint": "I test sono in tests/ o con #[cfg(test)]. Si eseguono con cargo test.",
        "src_dir": "src", "test_dir": "tests",
    },
    "javascript": {
        "ext": ".js",
        "system": "Sei uno sviluppatore JavaScript/Node.js senior. Scrivi codice moderno (ES2022+).",
        "test_cmd": ["npm", "test", "--silent"],
        "test_hint": "I test si eseguono con npm test (richiede package.json con script test).",
        "src_dir": "src", "test_dir": "tests",
    },
    "go": {
        "ext": ".go",
        "system": "Sei uno sviluppatore Go senior. Scrivi codice idiomatico, con errori espliciti.",
        "test_cmd": ["go", "test", "./..."],
        "test_hint": "I test sono nei file *_test.go. Si eseguono con go test ./...",
        "src_dir": ".", "test_dir": ".",
    },
}

_CURRENT_LANG = "python"

def set_language(lang):
    global _CURRENT_LANG
    if lang not in LANG_PROFILES:
        raise ValueError("Lingua non supportata: " + lang)
    _CURRENT_LANG = lang

def profile():
    return LANG_PROFILES[_CURRENT_LANG]

def llm(prompt, system=None):
    r = httpx.post(f"{OLLAMA}/api/chat", json={
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system or profile()["system"]},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 32768},
    }, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["message"]["content"]

def parse_json_block(text):
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
                    return json.loads(text[start:i+1])
                except Exception:
                    return None
    return None

def planner(state):
    p = profile()
    prompt = (
        "Leggi i requisiti e produci un piano JSON con la lista dei file da creare.\n\n"
        f"LINGUAGGIO: {_CURRENT_LANG}\n"
        f"ESTENSIONE: {p['ext']}\n"
        f"SRC_DIR: {p['src_dir']}\n"
        f"{p['test_hint']}\n\n"
        f"REQUISITI:\n{state['requirements']}\n\n"
        'Rispondi SOLO con JSON: {"files": [{"path": "...", "purpose": "...", "depends_on": []}]}'
    )
    resp = llm(prompt, system="Sei un architetto software. Rispondi solo JSON.")
    plan = parse_json_block(resp)
    if not plan or "files" not in plan:
        plan = {"files": [
            {"path": p['src_dir'] + "/main" + p['ext'], "purpose": "Implementa", "depends_on": []},
            {"path": p['test_dir'] + "/test_main" + p['ext'], "purpose": "Test", "depends_on": [p['src_dir'] + "/main" + p['ext']]},
        ]}
    return plan["files"]

def developer(state, file_spec, project_dir):
    path = project_dir / file_spec["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    context = ""
    for dep in file_spec.get("depends_on", []):
        dp = project_dir / dep
        if dp.exists():
            context += "\n--- " + dep + " ---\n" + dp.read_text() + "\n"
    prompt = (
        f"Scrivi il file `{file_spec['path']}` in {_CURRENT_LANG}.\n\n"
        f"SCOPO: {file_spec['purpose']}\n{context}\n"
        f"REQUISITI:\n{state['requirements'][:2000]}\n\n"
        "Rispondi SOLO con il contenuto del file, senza markdown fences."
    )
    content = llm(prompt).strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    path.write_text(content + "\n")
    return True

def tester(state, project_dir):
    p = profile()
    try:
        r = subprocess.run(p["test_cmd"], cwd=project_dir, capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    except subprocess.TimeoutExpired:
        return False, "Timeout 120s"
    except FileNotFoundError as e:
        return False, "Comando non trovato: " + str(e)

def bug_finder(state, project_dir, test_output):
    p = profile()
    files = [f for f in project_dir.rglob("*" + p['ext']) if ".orchestrator" not in str(f) and "target" not in str(f) and "node_modules" not in str(f)]
    if not files:
        return False
    dump = ""
    for f in files[:10]:
        try:
            dump += "\n--- " + str(f.relative_to(project_dir)) + " ---\n" + f.read_text()[:2000] + "\n"
        except Exception:
            pass
    prompt = (
        f"I test falliscono in un progetto {_CURRENT_LANG}. Output:\n\n{test_output}\n\n"
        f"File:\n{dump}\n\n"
        'Identifica il file sbagliato e riscrivilo. Rispondi SOLO con JSON: {"fixes": [{"path": "...", "new_content": "..."}]}'
    )
    resp = llm(prompt, system="Sei un debugger esperto. Rispondi solo JSON.")
    fixes = parse_json_block(resp)
    if not fixes or "fixes" not in fixes:
        return False
    for fix in fixes["fixes"]:
        target = project_dir / fix["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        content = fix["new_content"].strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        target.write_text(content + "\n")
    return True

def reviewer(state, project_dir):
    p = profile()
    dump = ""
    for f in project_dir.rglob("*" + p['ext']):
        if ".orchestrator" in str(f) or "target" in str(f):
            continue
        try:
            dump += "\n--- " + str(f.relative_to(project_dir)) + " ---\n" + f.read_text()[:1500] + "\n"
        except Exception:
            pass
    prompt = (
        f"Rivedi questo progetto {_CURRENT_LANG}.\n\nREQUISITI:\n{state['requirements']}\n\n"
        f"FILE:\n{dump[:6000]}\n\nRispondi una riga: APPROVED oppure REJECTED: <motivo>"
    )
    return llm(prompt).strip().split("\n")[0][:200]
