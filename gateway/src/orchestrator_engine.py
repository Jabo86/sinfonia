import json, subprocess, sys, time
from pathlib import Path
import httpx

OLLAMA = "http://localhost:11434"
MODEL = "qwen2.5-coder:7b-32k"
MAX_FIX_ATTEMPTS = 2
TIMEOUT = 600.0

LANG_PROFILES = {
    "python": {"ext": ".py", "system": "Sei uno sviluppatore Python senior.", "test_cmd": ["python3", "-m", "unittest", "discover", "tests/", "-v"], "test_hint": "Test con unittest.", "src_dir": "src", "test_dir": "tests"},
    "rust": {"ext": ".rs", "system": "Sei uno sviluppatore Rust senior.", "test_cmd": ["cargo", "test", "--quiet"], "test_hint": "Test con cargo test.", "src_dir": "src", "test_dir": "tests"},
    "javascript": {"ext": ".js", "system": "Sei uno sviluppatore JS senior.", "test_cmd": ["npm", "test", "--silent"], "test_hint": "Test con npm test.", "src_dir": "src", "test_dir": "tests"},
    "typescript": {"ext": ".ts", "system": "Sei uno sviluppatore TS senior.", "test_cmd": ["npx", "tsx", "--test", "tests/"], "test_hint": "Test con npx tsx.", "src_dir": "src", "test_dir": "tests"},
    "go": {"ext": ".go", "system": "Sei uno sviluppatore Go senior.", "test_cmd": ["go", "test", "./..."], "test_hint": "Test con go test.", "src_dir": ".", "test_dir": "."},
    "c": {"ext": ".c", "system": "Sei uno sviluppatore C senior.", "test_cmd": ["bash", "-c", "gcc -o /tmp/test src/*.c tests/*.c && /tmp/test"], "test_hint": "Test compilando con gcc.", "src_dir": "src", "test_dir": "tests"},
    "cpp": {"ext": ".cpp", "system": "Sei uno sviluppatore C++ senior.", "test_cmd": ["bash", "-c", "g++ -std=c++17 -o /tmp/test src/*.cpp tests/*.cpp && /tmp/test"], "test_hint": "Test compilando con g++", "src_dir": "src", "test_dir": "tests"},
    "java": {"ext": ".java", "system": "Sei uno sviluppatore Java senior.", "test_cmd": ["bash", "-c", "javac -d out src/*.java tests/*.java && java -cp out tests.Main"], "test_hint": "Test con javac", "src_dir": "src", "test_dir": "tests"},
    "csharp": {"ext": ".cs", "system": "Sei uno sviluppatore C# senior.", "test_cmd": ["dotnet", "test"], "test_hint": "Test con dotnet test", "src_dir": "src", "test_dir": "tests"},
    "php": {"ext": ".php", "system": "Sei uno sviluppatore PHP senior.", "test_cmd": ["php", "tests/test.php"], "test_hint": "Test con php", "src_dir": "src", "test_dir": "tests"},
    "ruby": {"ext": ".rb", "system": "Sei uno sviluppatore Ruby senior.", "test_cmd": ["ruby", "tests/test.rb"], "test_hint": "Test con ruby", "src_dir": "src", "test_dir": "tests"},
    "swift": {"ext": ".swift", "system": "Sei uno sviluppatore Swift senior.", "test_cmd": ["swift", "test"], "test_hint": "Test con swift test", "src_dir": "Sources", "test_dir": "Tests"},
    "kotlin": {"ext": ".kt", "system": "Sei uno sviluppatore Kotlin senior.", "test_cmd": ["bash", "-c", "kotlinc -include-runtime -d out.jar src/*.kt tests/*.kt && java -jar out.jar"], "test_hint": "Test con kotlinc", "src_dir": "src", "test_dir": "tests"},
    "scala": {"ext": ".scala", "system": "Sei uno sviluppatore Scala senior.", "test_cmd": ["sbt", "test"], "test_hint": "Test con sbt", "src_dir": "src", "test_dir": "tests"},
    "haskell": {"ext": ".hs", "system": "Sei uno sviluppatore Haskell senior.", "test_cmd": ["runhaskell", "tests/test.hs"], "test_hint": "Test con runhaskell", "src_dir": "src", "test_dir": "tests"},
    "elixir": {"ext": ".ex", "system": "Sei uno sviluppatore Elixir senior.", "test_cmd": ["mix", "test"], "test_hint": "Test con mix", "src_dir": "lib", "test_dir": "test"},
    "erlang": {"ext": ".erl", "system": "Sei uno sviluppatore Erlang senior.", "test_cmd": ["rebar3", "eunit"], "test_hint": "Test con rebar3", "src_dir": "src", "test_dir": "test"},
    "clojure": {"ext": ".clj", "system": "Sei uno sviluppatore Clojure senior.", "test_cmd": ["lein", "test"], "test_hint": "Test con lein", "src_dir": "src", "test_dir": "test"},
    "fsharp": {"ext": ".fs", "system": "Sei uno sviluppatore F# senior.", "test_cmd": ["dotnet", "test"], "test_hint": "Test con dotnet", "src_dir": "src", "test_dir": "tests"},
    "ocaml": {"ext": ".ml", "system": "Sei uno sviluppatore OCaml senior.", "test_cmd": ["dune", "test"], "test_hint": "Test con dune", "src_dir": "src", "test_dir": "tests"},
    "perl": {"ext": ".pl", "system": "Sei uno sviluppatore Perl senior.", "test_cmd": ["perl", "tests/test.pl"], "test_hint": "Test con perl", "src_dir": "src", "test_dir": "tests"},
    "lua": {"ext": ".lua", "system": "Sei uno sviluppatore Lua senior.", "test_cmd": ["lua", "tests/test.lua"], "test_hint": "Test con lua", "src_dir": "src", "test_dir": "tests"},
    "r": {"ext": ".R", "system": "Sei uno sviluppatore R senior.", "test_cmd": ["Rscript", "tests/test.R"], "test_hint": "Test con Rscript", "src_dir": "src", "test_dir": "tests"},
    "julia": {"ext": ".jl", "system": "Sei uno sviluppatore Julia senior.", "test_cmd": ["julia", "tests/test.jl"], "test_hint": "Test con julia", "src_dir": "src", "test_dir": "tests"},
    "dart": {"ext": ".dart", "system": "Sei uno sviluppatore Dart senior.", "test_cmd": ["dart", "test"], "test_hint": "Test con dart", "src_dir": "lib", "test_dir": "test"},
    "zig": {"ext": ".zig", "system": "Sei uno sviluppatore Zig senior.", "test_cmd": ["zig", "build", "test"], "test_hint": "Test con zig", "src_dir": "src", "test_dir": "tests"},
    "nim": {"ext": ".nim", "system": "Sei uno sviluppatore Nim senior.", "test_cmd": ["nim", "c", "-r", "tests/test.nim"], "test_hint": "Test con nim", "src_dir": "src", "test_dir": "tests"},
    "crystal": {"ext": ".cr", "system": "Sei uno sviluppatore Crystal senior.", "test_cmd": ["crystal", "spec"], "test_hint": "Test con crystal", "src_dir": "src", "test_dir": "spec"},
    "v": {"ext": ".v", "system": "Sei uno sviluppatore V senior.", "test_cmd": ["v", "test", "tests/"], "test_hint": "Test con v", "src_dir": "src", "test_dir": "tests"},
    "odin": {"ext": ".odin", "system": "Sei uno sviluppatore Odin senior.", "test_cmd": ["odin", "test", "tests/"], "test_hint": "Test con odin", "src_dir": "src", "test_dir": "tests"},
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
        "model": MODEL, "messages": [{"role": "system", "content": system or profile()["system"]}, {"role": "user", "content": prompt}],
        "stream": False, "options": {"temperature": 0.2, "num_ctx": 32768}
    }, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["message"]["content"]

def parse_json_block(text):
    start = text.find("{")
    if start < 0: start = text.find("[")
    if start < 0: return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] in "{[":
            depth += 1
        elif text[i] in "}]":
            depth -= 1
            if depth == 0:
                try: return json.loads(text[start:i+1])
                except: return None
    return None

def planner(state):
    p = profile()
    prompt = f"Leggi i requisiti e produci un piano JSON.\nLINGUAGGIO: {_CURRENT_LANG}\nESTENSIONE: {p['ext']}\nSRC_DIR: {p['src_dir']}\n{p['test_hint']}\n\nREQUISITI:\n{state['requirements']}\n\nRispondi SOLO con JSON: {{\"files\": [{{\"path\": \"...\", \"purpose\": \"...\", \"depends_on\": []}}]}}"
    resp = llm(prompt, system="Sei un architetto. Rispondi solo JSON.")
    plan = parse_json_block(resp)
    if not plan or "files" not in plan:
        plan = {"files": [{"path": p['src_dir'] + "/main" + p['ext'], "purpose": "Implementa", "depends_on": []}]}
    return plan["files"]

def developer(state, file_spec, project_dir):
    path = project_dir / file_spec["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    context = "".join([f"\n--- {d} ---\n{(project_dir/d).read_text()}" for d in file_spec.get("depends_on", []) if (project_dir/d).exists()])
    prompt = f"Scrivi il file `{file_spec['path']}` in {_CURRENT_LANG}.\nSCOPO: {file_spec['purpose']}\n{context}\nREQUISITI:\n{state['requirements'][:2000]}\n\nRispondi SOLO col codice, senza markdown fences."
    content = llm(prompt).strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    path.write_text(content + "\n")

def tester(state, project_dir):
    p = profile()
    try:
        r = subprocess.run(p["test_cmd"], cwd=project_dir, capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    except subprocess.TimeoutExpired: return False, "Timeout 120s"
    except FileNotFoundError as e: return False, "Toolchain non installata: " + str(e)

def bug_finder(state, project_dir, out):
    p = profile()
    files = [f for f in project_dir.rglob("*" + p['ext']) if "target" not in str(f) and "node_modules" not in str(f) and ".orchestrator" not in str(f)]
    if not files: return False
    dump = "".join([f"\n--- {f.relative_to(project_dir)} ---\n{f.read_text()[:2000]}" for f in files[:5]])
    prompt = f"Test falliti. Output:\n{out}\nFile:\n{dump}\n\nRispondi SOLO JSON: {{\"fixes\": [{{\"path\": \"...\", \"new_content\": \"...\"}}]}}"
    fixes = parse_json_block(llm(prompt, system="Sei un debugger. JSON only."))
    if not fixes or "fixes" not in fixes: return False
    for fix in fixes["fixes"]:
        t = project_dir / fix["path"]
        t.parent.mkdir(parents=True, exist_ok=True)
        c = fix["new_content"].strip()
        if c.startswith("```"): c = "\n".join(c.split("\n")[1:-1])
        t.write_text(c + "\n")
    return True

def reviewer(state, project_dir):
    p = profile()
    files = [f for f in project_dir.rglob("*" + p['ext']) if "target" not in str(f) and "node_modules" not in str(f)]
    dump = "".join([f"\n--- {f.relative_to(project_dir)} ---\n{f.read_text()[:1500]}" for f in files[:5]])
    prompt = f"Rivedi progetto {_CURRENT_LANG}.\nREQ:\n{state['requirements']}\nFILE:\n{dump}\nRispondi: APPROVED o REJECTED: motivo"
    return llm(prompt).strip().split("\n")[0][:200]
