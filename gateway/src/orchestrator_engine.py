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
    "typescript": {
        "ext": ".ts",
        "system": "Sei uno sviluppatore TypeScript senior. Usa tipi stretti, evita any.",
        "test_cmd": ["npx", "tsx", "--test", "tests/"],
        "test_hint": "I test sono in tests/*.ts e si eseguono con npx tsx --test tests/.",
        "src_dir": "src", "test_dir": "tests",
    },
    "go": {
        "ext": ".go",
        "system": "Sei uno sviluppatore Go senior. Scrivi codice idiomatico, con errori espliciti.",
        "test_cmd": ["go", "test", "./..."],
        "test_hint": "I test sono nei file *_test.go. Si eseguono con go test ./...",
        "src_dir": ".", "test_dir": ".",
    },
    "c": {
        "ext": ".c",
        "system": "Sei uno sviluppatore C senior. Scrivi codice portabile, senza warning con -Wall -Wextra.",
        "test_cmd": ["bash", "-c", "gcc -o /tmp/test src/*.c tests/*.c && /tmp/test"],
        "test_hint": "I test sono in tests/. Compila con gcc o usa make test.",
        "src_dir": "src", "test_dir": "tests",
    },
    "cpp": {
        "ext": ".cpp",
        "system": "Sei uno sviluppatore C++ senior. Scrivi codice moderno (C++17/20), senza memory leak.",
        "test_cmd": ["bash", "-c", "g++ -std=c++17 -o /tmp/test src/*.cpp tests/*.cpp && /tmp/test"],
        "test_hint": "I test sono in tests/. Compila con g++ -std=c++17.",
        "src_dir": "src", "test_dir": "tests",
    },
    "java": {
        "ext": ".java",
        "system": "Sei uno sviluppatore Java senior. Usa Java 17+, niente dipendenze esterne.",
        "test_cmd": ["bash", "-c", "javac -d out src/*.java tests/*.java && java -cp out tests.Main"],
        "test_hint": "I test sono in tests/. Compila con javac.",
        "src_dir": "src", "test_dir": "tests",
    },
    "csharp": {
        "ext": ".cs",
        "system": "Sei uno sviluppatore C# senior. Scrivi codice .NET moderno (C# 10+).",
        "test_cmd": ["dotnet", "test"],
        "test_hint": "I test si eseguono con dotnet test (richiede un progetto di test .csproj).",
        "src_dir": "src", "test_dir": "tests",
    },
    "php": {
        "ext": ".php",
        "system": "Sei uno sviluppatore PHP senior. Scrivi codice moderno (PHP 8+), senza dipendenze inutili.",
        "test_cmd": ["php", "tests/test.php"],
        "test_hint": "I test si eseguono con php tests/test.php.",
        "src_dir": "src", "test_dir": "tests",
    },
    "ruby": {
        "ext": ".rb",
        "system": "Sei uno sviluppatore Ruby senior. Scrivi codice idiomatico, con test in RSpec o Minitest.",
        "test_cmd": ["ruby", "tests/test.rb"],
        "test_hint": "I test si eseguono con ruby tests/test.rb.",
        "src_dir": "src", "test_dir": "tests",
    },
    "swift": {
        "ext": ".swift",
        "system": "Sei uno sviluppatore Swift senior. Scrivi codice idiomatico, con test in XCTest.",
        "test_cmd": ["swift", "test"],
        "test_hint": "I test si eseguono con swift test (richiede Package.swift).",
        "src_dir": "Sources", "test_dir": "Tests",
    },
    "kotlin": {
        "ext": ".kt",
        "system": "Sei uno sviluppatore Kotlin senior. Scrivi codice idiomatico, con test in JUnit.",
        "test_cmd": ["bash", "-c", "kotlinc -include-runtime -d out.jar src/*.kt tests/*.kt && java -jar out.jar"],
        "test_hint": "I test si eseguono compilando con kotlinc e eseguendo il jar.",
        "src_dir": "src", "test_dir": "tests",
    },
    "scala": {
        "ext": ".scala",
        "system": "Sei uno sviluppatore Scala senior. Scrivi codice funzionale, con test in ScalaTest.",
        "test_cmd": ["sbt", "test"],
        "test_hint": "I test si eseguono con sbt test (richiede build.sbt).",
        "src_dir": "src", "test_dir": "tests",
    },
    "haskell": {
        "ext": ".hs",
        "system": "Sei uno sviluppatore Haskell senior. Scrivi codice funzionale puro, con test in HUnit.",
        "test_cmd": ["runhaskell", "tests/test.hs"],
        "test_hint": "I test si eseguono con runhaskell tests/test.hs.",
        "src_dir": "src", "test_dir": "tests",
    },
    "elixir": {
        "ext": ".ex",
        "system": "Sei uno sviluppatore Elixir senior. Scrivi codice idiomatico, con test in ExUnit.",
        "test_cmd": ["mix", "test"],
        "test_hint": "I test si eseguono con mix test (richiede mix.exs).",
        "src_dir": "lib", "test_dir": "test",
    },
    "erlang": {
        "ext": ".erl",
        "system": "Sei uno sviluppatore Erlang senior. Scrivi codice idiomatico, con test in EUnit.",
        "test_cmd": ["rebar3", "eunit"],
        "test_hint": "I test si eseguono con rebar3 eunit (richiede rebar.config).",
        "src_dir": "src", "test_dir": "test",
    },
    "clojure": {
        "ext": ".clj",
        "system": "Sei uno sviluppatore Clojure senior. Scrivi codice funzionale, con test in clojure.test.",
        "test_cmd": ["lein", "test"],
        "test_hint": "I test si eseguono con lein test (richiede project.clj).",
        "src_dir": "src", "test_dir": "test",
    },
    "fsharp": {
        "ext": ".fs",
        "system": "Sei uno sviluppatore F# senior. Scrivi codice funzionale, con test in xUnit.",
        "test_cmd": ["dotnet", "test"],
        "test_hint": "I test si eseguono con dotnet test (richiede .fsproj).",
        "src_dir": "src", "test_dir": "tests",
    },
    "ocaml": {
        "ext": ".ml",
        "system": "Sei uno sviluppatore OCaml senior. Scrivi codice funzionale, con test in OUnit.",
        "test_cmd": ["dune", "test"],
        "test_hint": "I test si eseguono con dune test (richiede dune-project).",
        "src_dir": "src", "test_dir": "tests",
    },
    "perl": {
        "ext": ".pl",
        "system": "Sei uno sviluppatore Perl senior. Scrivi codice moderno (Perl 5.30+), con test in Test::More.",
        "test_cmd": ["perl", "tests/test.pl"],
        "test_hint": "I test si eseguono con perl tests/test.pl.",
        "src_dir": "src", "test_dir": "tests",
    },
    "lua": {
        "ext": ".lua",
        "system": "Sei uno sviluppatore Lua senior. Scrivi codice idiomatico, con test in busted.",
        "test_cmd": ["lua", "tests/test.lua"],
        "test_hint": "I test si eseguono con lua tests/test.lua.",
        "src_dir": "src", "test_dir": "tests",
    },
    "r": {
        "ext": ".R",
        "system": "Sei uno sviluppatore R senior. Scrivi codice vettorizzato, con test in testthat.",
        "test_cmd": ["Rscript", "tests/test.R"],
        "test_hint": "I test si eseguono con Rscript tests/test.R.",
        "src_dir": "src", "test_dir": "tests",
    },
    "julia": {
        "ext": ".jl",
        "system": "Sei uno sviluppatore Julia senior. Scrivi codice performante, con test in Test.",
        "test_cmd": ["julia", "tests/test.jl"],
        "test_hint": "I test si eseguono con julia tests/test.jl.",
        "src_dir": "src", "test_dir": "tests",
    },
    "dart": {
        "ext": ".dart",
        "system": "Sei uno sviluppatore Dart senior. Scrivi codice idiomatico, con test in test package.",
        "test_cmd": ["dart", "test"],
        "test_hint": "I test si eseguono con dart test.",
        "src_dir": "lib", "test_dir": "test",
    },
    "zig": {
        "ext": ".zig",
        "system": "Sei uno sviluppatore Zig senior. Scrivi codice sicuro, con test integrati.",
        "test_cmd": ["zig", "build", "test"],
        "test_hint": "I test si eseguono con zig build test.",
        "src_dir": "src", "test_dir": "tests",
    },
    "nim": {
        "ext": ".nim",
        "system": "Sei uno sviluppatore Nim senior. Scrivi codice leggibile, con test in unittest.",
        "test_cmd": ["nim", "c", "-r", "tests/test.nim"],
        "test_hint": "I test si eseguono con nim c -r tests/test.nim.",
        "src_dir": "src", "test_dir": "tests",
    },
    "crystal": {
        "ext": ".cr",
        "system": "Sei uno sviluppatore Crystal senior. Scrivi codice idiomatico, con test in Spec.",
        "test_cmd": ["crystal", "spec"],
        "test_hint": "I test si eseguono con crystal spec.",
        "src_dir": "src", "test_dir": "spec",
    },
    "v": {
        "ext": ".v",
        "system": "Sei uno sviluppatore V senior. Scrivi codice semplice e sicuro.",
        "test_cmd": ["v", "test", "tests/"],
        "test_hint": "I test si eseguono con v test tests/.",
        "src_dir": "src", "test_dir": "tests",
    },
    "odin": {
        "ext": ".odin",
        "system": "Sei uno sviluppatore Odin senior. Scrivi codice idiomatico.",
        "test_cmd": ["odin", "test", "tests/"],
        "test_hint": "I test si eseguono con odin test tests/.",
        "src_dir": "src", "test_dir": "tests",
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
