// --- Stato ---
const API = "";
const state = {
  conversations: [],
  currentId: null,
  messages: [],
};

const $ = (sel) => document.querySelector(sel);

// --- HTTP helpers ---
async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

// --- Normalizza LaTeX prima di marked ---
function normalizeLatex(content) {
  let result = content;
  // \[...\] -> $$...$$
  result = result.split("\\[").join("$$");
  result = result.split("\\]").join("$$");
  // \(...\) -> $...$
  result = result.split("\\(").join("$");
  result = result.split("\\)").join("$");
  return result;
}

// --- Health check ---
async function checkHealth() {
  const dot = $("#status-dot");
  const txt = $("#status-text");
  if (!dot || !txt) return;
  try {
    const data = await api("/health");
    dot.className = "status-dot ok";
    txt.textContent = `${data.free_providers} free · ${data.paid_providers} paid`;
  } catch (e) {
    dot.className = "status-dot err";
    txt.textContent = "server offline";
  }
}

// --- Modelli ---
async function loadModels() {
  try {
    const data = await api("/v1/models");
    const sel = $("#model-select");
    if (!sel) return;
    sel.innerHTML = "";
    const auto = document.createElement("option");
    auto.value = "sinfonia/auto";
    auto.textContent = "🎼 Sinfonia Auto";
    sel.appendChild(auto);
    for (const m of data.data) {
      if (m.id === "sinfonia/auto") continue;
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.id.replace("sinfonia/", "").replace("/", " · ");
      sel.appendChild(opt);
    }
  } catch (e) {
    console.error("Errore caricamento modelli:", e);
  }
}

// --- Crediti ---
async function loadCredits() {
  try {
    const data = await api("/v1/credits");
    const container = document.getElementById("credits-list");
    if (!container) return;
    container.innerHTML = "";
    for (const [pid, info] of Object.entries(data)) {
      const div = document.createElement("div");
      div.className = "credit-item";
      if (info.type === "free") {
        if (!info.available && info.in_cooldown) {
          div.classList.add("err");
          div.innerHTML = '<span class="credit-name">' + info.name + '</span><span class="credit-value">⏸ ' + info.cooldown_seconds + 's</span>';
        } else {
          const pct = info.rpd_limit ? info.rpd_percent : 100;
          const cls = pct > 50 ? "ok" : (pct > 10 ? "warn" : "err");
          div.classList.add(cls);
          const used = info.rpd_limit ? (info.rpd_used + "/" + info.rpd_limit) : (info.rpd_used + "/∞");
          div.innerHTML = '<span class="credit-name">' + info.name + '</span><span class="credit-value">' + used + '<span class="credit-pct">' + Math.round(pct) + '%</span></span>';
        }
      } else {
        div.classList.add("paid");
        const remaining = info.budget_remaining_usd != null ? info.budget_remaining_usd.toFixed(2) : "?";
        div.innerHTML = '<span class="credit-name">' + info.name + '</span><span class="credit-value">$' + remaining + '</span>';
      }
      container.appendChild(div);
    }
  } catch (e) {
    console.error("Errore crediti:", e);
  }
}

// --- Provider indicator ---
function showProvider(provider, tokens, elapsed) {
  const el = document.getElementById("provider-indicator");
  if (!el) return;
  el.innerHTML = '<span class="badge live">🎼 ' + provider + '</span> ' + tokens + ' token · ' + elapsed + 's';
}

function clearProvider() {
  const el = document.getElementById("provider-indicator");
  if (el) el.innerHTML = "";
}

// --- Init Mermaid ---
let mermaidReady = false;
function initMermaid() {
  if (mermaidReady || typeof mermaid === "undefined") return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    securityLevel: "loose",
    fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif",
  });
  mermaidReady = true;
}

// --- Escape HTML ---
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, function(c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

// --- Rendering Markdown + KaTeX + Mermaid ---
async function renderContent(el, rawContent) {
  // 1. Normalizza i delimitatori LaTeX PRIMA di marked
  const content = normalizeLatex(rawContent);

  // 2. Parse markdown
  if (typeof marked !== "undefined") {
    try {
      el.innerHTML = marked.parse(content);
    } catch (e) {
      el.innerHTML = "<pre>" + escapeHtml(content) + "</pre>";
    }
  } else {
    el.innerHTML = "<pre>" + escapeHtml(content) + "</pre>";
  }

    // 0. SVG inline: blocchi ```svg
  const svgCodes = el.querySelectorAll("code.language-svg");
  for (const code of svgCodes) {
    const src = code.textContent;
    const container = document.createElement("div");
    container.className = "svg-figure";
    const parent = code.closest("pre") || code;
    parent.replaceWith(container);
    try {
      container.innerHTML = src;
    } catch (e) {
      container.innerHTML = '<div class="mermaid-error">Errore SVG</div>';
    }
  }

// 3. Mermaid: sostituisci i blocchi ```mermaid
  const mermaidCodes = el.querySelectorAll("code.language-mermaid, code.mermaid");
  for (const code of mermaidCodes) {
    const src = code.textContent;
    const container = document.createElement("div");
    container.className = "mermaid";
    const id = "mermaid-" + Math.random().toString(36).slice(2, 10);
    container.id = id;
    const parent = code.closest("pre") || code;
    parent.replaceWith(container);

    try {
      if (typeof mermaid !== "undefined") {
        const result = await mermaid.render(id + "-svg", src);
        container.innerHTML = result.svg;
      } else {
        container.innerHTML = '<div class="mermaid-error">Mermaid non caricato</div>';
      }
    } catch (e) {
      container.innerHTML = '<div class="mermaid-error">Diagramma non renderizzabile</div>';
    }
  }

  // 4. KaTeX auto-render su tutto il resto
  if (typeof renderMathInElement !== "undefined") {
    try {
      renderMathInElement(el, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\[", right: "\\]", display: true },
          { left: "\\(", right: "\\)", display: false }
        ],
        throwOnError: false,
        errorColor: "#f87171",
      });
    } catch (e) {
      console.warn("KaTeX render error:", e);
    }
  }
}

// --- Render messaggi ---
function renderMessages() {
  const container = $("#messages");
  if (!container) return;
  if (state.messages.length === 0) {
    container.innerHTML = '<div class="welcome"><h1>🎼 Benvenuto in Sinfonia</h1><p>L\'orchestrazione etica dell\'intelligenza artificiale.</p><p class="hint">Scrivi un messaggio qui sotto per iniziare.</p></div>';
    return;
  }
  container.innerHTML = "";
  for (const msg of state.messages) {
    const div = document.createElement("div");
    div.className = "message " + msg.role + (msg.error ? " error" : "");

    const body = document.createElement("div");
    body.className = "message-body";

    if (msg.content) {
      renderContent(body, msg.content);
    }

    div.appendChild(body);

    if (msg.meta) {
      const meta = document.createElement("div");
      meta.className = "message-meta";
      meta.textContent = msg.meta;
      div.appendChild(meta);
    }

    container.appendChild(div);
  }
  container.scrollTop = container.scrollHeight;
}

function addMessage(role, content, meta, error) {
  state.messages.push({ role: role, content: content, meta: meta || null, error: error || false });
  renderMessages();
}

// --- Sidebar ---
function renderConversations() {
  const container = $("#conversations");
  if (!container) return;
  container.innerHTML = "";
  for (const c of state.conversations) {
    const div = document.createElement("div");
    div.className = "conv-item" + (c.id === state.currentId ? " active" : "");
    div.textContent = c.title || "Nuova chat";
    div.onclick = function() { loadConversation(c.id); };
    container.appendChild(div);
  }
}

function saveConversation() {
  if (state.messages.length === 0) return;
  const firstUser = state.messages.find(function(m) { return m.role === "user"; });
  const title = firstUser ? firstUser.content.slice(0, 40) : "Nuova chat";
  const existing = state.conversations.find(function(c) { return c.id === state.currentId; });
  if (existing) {
    existing.title = title;
    existing.messages = state.messages.slice();
  } else if (state.currentId) {
    state.conversations.unshift({
      id: state.currentId,
      title: title,
      messages: state.messages.slice(),
    });
  }
  localStorage.setItem("sinfonia.conversations", JSON.stringify(state.conversations));
  renderConversations();
}

function loadConversation(id) {
  const conv = state.conversations.find(function(c) { return c.id === id; });
  if (!conv) return;
  state.currentId = id;
  state.messages = conv.messages.slice();
  renderMessages();
  renderConversations();
}

function newChat() {
  state.currentId = null;
  state.messages = [];
  renderMessages();
  renderConversations();
  const input = $("#input");
  if (input) input.focus();
}

// --- Invio ---
async function sendMessage(text) {
  const ensemble = $("#ensemble-mode").checked;
  const model = $("#model-select").value;

  clearProvider();
  addMessage("user", text);
  $("#input").value = "";
  $("#input").style.height = "auto";
  $("#send").disabled = true;

  const placeholder = { role: "assistant", content: "", meta: null };
  state.messages.push(placeholder);
  renderMessages();

  const messagesContainer = $("#messages");
  const lastMsg = messagesContainer.lastElementChild;
  if (lastMsg) lastMsg.classList.add("typing");

  const t0 = Date.now();

  try {
    let data;
    if (ensemble) {
      data = await api("/v1/ensemble", {
        method: "POST",
        body: JSON.stringify({ messages: [{ role: "user", content: text }] }),
      });
      placeholder.content = data.final_content;
      placeholder.meta = "ensemble · giudice " + data.judge_model + " · " + data.successful_panels + "/" + data.total_panels + " panel · " + ((Date.now()-t0)/1000).toFixed(1) + "s";
      showProvider("ensemble (" + data.successful_panels + " AI + giudice)", data.total_tokens, ((Date.now()-t0)/1000).toFixed(1));
    } else {
      const payload = {
        model: model,
        messages: [{ role: "user", content: text }],
      };
      if (state.currentId) payload.conversation_id = state.currentId;

      data = await api("/v1/chat/completions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      placeholder.content = data.choices[0].message.content;
      state.currentId = data.conversation_id || state.currentId;
      const provider = (data.model || "").replace("sinfonia/", "");
      const tokens = data.usage && data.usage.total_tokens ? data.usage.total_tokens : 0;
      placeholder.meta = provider + " · " + tokens + " token · " + ((Date.now()-t0)/1000).toFixed(1) + "s";
      showProvider(provider, tokens, ((Date.now()-t0)/1000).toFixed(1));
    }
  } catch (e) {
    placeholder.content = "Errore: " + e.message;
    placeholder.error = true;
  } finally {
    if (lastMsg) lastMsg.classList.remove("typing");
    renderMessages();
    saveConversation();
    $("#send").disabled = false;
    $("#input").focus();
  }
}

// --- Init ---
function init() {
  try {
    const saved = localStorage.getItem("sinfonia.conversations");
    if (saved) state.conversations = JSON.parse(saved);
  } catch (e) {}
  renderConversations();

  initMermaid();
  checkHealth();
  loadModels();
  loadCredits();
  setInterval(loadCredits, 30000);
  setInterval(checkHealth, 30000);

  $("#new-chat").onclick = newChat;
  $("#composer").onsubmit = function(e) {
    e.preventDefault();
    const text = $("#input").value.trim();
    if (!text) return;
    sendMessage(text);
  };

  const input = $("#input");
  input.addEventListener("input", function() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 200) + "px";
  });
  input.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("#composer").requestSubmit();
    }
  });
}

document.addEventListener("DOMContentLoaded", init);
