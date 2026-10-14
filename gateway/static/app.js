/* ============================================================
   SINFONIA — APP 2026
   ============================================================ */

const API = "";
const state = {
  conversations: [],
  currentId: null,
  messages: [],
  currentModel: "sinfonia/auto",
  models: [],
  ensemble: false,
  isGenerating: false,
  searchQuery: "",
};

const $ = (sel) => document.querySelector(sel);

/* ---------- HTTP ---------- */
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

/* ---------- Toast ---------- */
function toast(message, type = "info", duration = 3000) {
  const container = $("#toast-container");
  if (!container) return;
  const icons = { success: "\u2713", error: "\u2715", info: "\u2139" };
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span style="font-size:16px;">${icons[type] || "\u2139"}</span><span>${escapeHtml(message)}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add("removing");
    setTimeout(() => el.remove(), 300);
  }, duration);
}

/* ---------- Escape ---------- */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

/* ---------- Health ---------- */
async function checkHealth() {
  const dot = $("#status-pill .status-dot");
  const txt = $("#status-text");
  if (!dot || !txt) return;
  try {
    const data = await api("/health");
    dot.className = "status-dot ok";
    txt.textContent = `${data.free_providers} provider \u00b7 ${data.paid_providers} premium`;
  } catch (e) {
    dot.className = "status-dot err";
    txt.textContent = "Server offline";
  }
}

/* ---------- Modelli ---------- */
async function loadModels() {
  try {
    const data = await api("/v1/models");
    state.models = data.data || [];
    renderModelDropdown();
  } catch (e) {
    console.error("Errore caricamento modelli:", e);
  }
}

function renderModelDropdown() {
  const dropdown = $("#model-dropdown");
  if (!dropdown) return;
  dropdown.innerHTML = "";

  const autoGroup = document.createElement("div");
  autoGroup.innerHTML = `<div class="model-group-label">Consigliato</div>`;
  const autoOpt = document.createElement("div");
  autoOpt.className = "model-option" + (state.currentModel === "sinfonia/auto" ? " selected" : "");
  autoOpt.innerHTML = `<span style="font-size:16px;">\ud83c\udfbc</span><span>Sinfonia Auto</span>`;
  autoOpt.onclick = () => selectModel("sinfonia/auto", "Sinfonia Auto", "\ud83c\udfbc");
  autoGroup.appendChild(autoOpt);
  dropdown.appendChild(autoGroup);

  const byProvider = {};
  for (const m of state.models) {
    if (m.id === "sinfonia/auto") continue;
    const parts = m.id.split("/");
    const provider = parts[1] || "other";
    if (!byProvider[provider]) byProvider[provider] = [];
    byProvider[provider].push(m);
  }

  for (const [provider, models] of Object.entries(byProvider)) {
    const group = document.createElement("div");
    group.innerHTML = `<div class="model-group-label">${provider}</div>`;
    for (const m of models.slice(0, 8)) {
      const opt = document.createElement("div");
      opt.className = "model-option" + (state.currentModel === m.id ? " selected" : "");
      const modelName = m.id.replace(`sinfonia/${provider}/`, "");
      opt.innerHTML = `<span>${escapeHtml(modelName)}</span><span class="model-option-provider">${provider}</span>`;
      opt.onclick = () => selectModel(m.id, modelName, "\ud83e\udd16");
      group.appendChild(opt);
    }
    dropdown.appendChild(group);
  }
}

function selectModel(id, name, avatar) {
  state.currentModel = id;
  const nameEl = $("#model-name");
  const avatarEl = $("#model-avatar");
  if (nameEl) nameEl.textContent = name;
  if (avatarEl) avatarEl.textContent = avatar;
  const dd = $("#model-dropdown");
  if (dd) dd.classList.remove("open");
  renderModelDropdown();
}

/* ---------- Crediti ---------- */
async function loadCredits() {
  try {
    const data = await api("/v1/credits");
    const container = $("#credits-list");
    if (!container) return;
    container.innerHTML = "";

    for (const [pid, info] of Object.entries(data)) {
      if (info.type === "paid" && (info.budget_remaining_usd === null || info.budget_remaining_usd === undefined)) continue;

      const div = document.createElement("div");
      div.className = "credit-item";

      let dotClass = "ok";
      let value = "";

      if (info.type === "free") {
        if (!info.available && info.in_cooldown) {
          dotClass = "err";
          value = `\u23f8 ${info.cooldown_seconds}s`;
        } else if (info.available) {
          if (info.rpd_limit) {
            const pct = info.rpd_percent;
            dotClass = pct > 50 ? "ok" : (pct > 10 ? "warn" : "err");
            value = `${info.rpd_used}/${info.rpd_limit}`;
          } else {
            value = `${info.rpd_used}`;
          }
        } else {
          dotClass = "err";
          value = "esaurito";
        }
      } else {
        dotClass = "ok";
        value = `$${(info.budget_remaining_usd || 0).toFixed(2)}`;
      }

      div.innerHTML = `
        <span class="credit-dot ${dotClass}"></span>
        <span class="credit-name">${escapeHtml(info.name)}</span>
        <span class="credit-value">${value}</span>
      `;
      container.appendChild(div);
    }
  } catch (e) {
    console.error("Errore crediti:", e);
  }
}

/* ---------- Provider indicator ---------- */
function showProvider(provider, tokens, elapsed) {
  const el = $("#provider-indicator");
  if (!el) return;
  const providerName = provider.split("/")[0] || provider;
  el.innerHTML = `
    <span class="provider-badge live">
      <span style="width:6px;height:6px;border-radius:50%;background:currentColor;"></span>
      ${escapeHtml(providerName)}
    </span>
    <span style="color:var(--text-tertiary);font-size:11px;">${tokens} token \u00b7 ${elapsed}s</span>
  `;
}

function clearProvider() {
  const el = $("#provider-indicator");
  if (el) el.innerHTML = "";
}

/* ---------- Mermaid ---------- */
let mermaidReady = false;
function initMermaid() {
  if (mermaidReady || typeof mermaid === "undefined") return;
  mermaid.initialize({
    startOnLoad: false,
    theme: document.documentElement.getAttribute("data-theme") === "light" ? "default" : "dark",
    securityLevel: "loose",
  });
  mermaidReady = true;
}

/* ---------- Rendering content ---------- */
async function renderContent(el, rawContent) {
  if (typeof marked !== "undefined") {
    try {
      el.innerHTML = marked.parse(rawContent);
    } catch (e) {
      el.innerHTML = "<pre>" + escapeHtml(rawContent) + "</pre>";
    }
  } else {
    el.innerHTML = "<pre>" + escapeHtml(rawContent) + "</pre>";
  }

  if (typeof hljs !== "undefined") {
    el.querySelectorAll("pre code").forEach((block) => {
      const cls = block.className || "";
      if (!cls.includes("language-mermaid") && !cls.includes("language-svg")) {
        try { hljs.highlightElement(block); } catch (e) {}
      }
    });
  }

  el.querySelectorAll("pre").forEach((pre) => {
    const code = pre.querySelector("code");
    if (!code || pre.querySelector(".code-header")) return;
    const langMatch = (code.className || "").match(/language-(\w+)/);
    const lang = langMatch ? langMatch[1] : "code";
    if (lang === "mermaid" || lang === "svg") return;

    const header = document.createElement("div");
    header.className = "code-header";
    header.innerHTML = `<span>${lang}</span><button class="code-copy" onclick="copyCode(this)">Copia</button>`;
    pre.insertBefore(header, pre.firstChild);
  });

  const svgCodes = el.querySelectorAll("code.language-svg");
  for (const code of svgCodes) {
    const src = code.textContent;
    const container = document.createElement("div");
    container.className = "svg-figure";
    const parent = code.closest("pre") || code;
    parent.replaceWith(container);
    try { container.innerHTML = src; } catch (e) {}
  }

  const mermaidCodes = el.querySelectorAll("code.language-mermaid, code.mermaid");
  for (const code of mermaidCodes) {
    const src = code.textContent;
    const container = document.createElement("div");
    container.className = "mermaid";
    const id = "m-" + Math.random().toString(36).slice(2, 10);
    container.id = id;
    const parent = code.closest("pre") || code;
    parent.replaceWith(container);
    try {
      if (typeof mermaid !== "undefined") {
        const result = await mermaid.render(id + "-svg", src);
        container.innerHTML = result.svg;
      }
    } catch (e) {
      container.innerHTML = '<div class="mermaid-error">Diagramma non renderizzabile</div>';
    }
  }

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
      });
    } catch (e) {}
  }
}

window.copyCode = function(btn) {
  const pre = btn.closest("pre");
  const code = pre.querySelector("code");
  navigator.clipboard.writeText(code.textContent).then(() => {
    btn.textContent = "\u2713 Copiato";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = "Copia";
      btn.classList.remove("copied");
    }, 1500);
  });
};

/* ---------- Render messaggi ---------- */
function renderMessages() {
  const container = $("#messages");
  if (!container) return;

  if (state.messages.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-logo">\ud83c\udfbc</div>
        <h1>Sinfonia</h1>
        <p class="empty-subtitle">L'orchestrazione etica dell'intelligenza artificiale</p>
        <div class="suggestions" id="suggestions">
          <button class="suggestion" data-prompt="Spiega la fotosintesi clorofilliana in modo semplice">
            <div class="sugg-icon">\ud83d\udcda</div>
            <div class="sugg-text"><strong>Spiega un concetto</strong><span>La fotosintesi clorofilliana</span></div>
          </button>
          <button class="suggestion" data-prompt="Scrivi una funzione Python che calcola i numeri primi">
            <div class="sugg-icon">\ud83d\udcbb</div>
            <div class="sugg-text"><strong>Scrivi codice</strong><span>Numeri primi in Python</span></div>
          </button>
          <button class="suggestion" data-prompt="Traduci in inglese: il mio nome e Fabio e vivo a Roma">
            <div class="sugg-icon">\ud83c\udf10</div>
            <div class="sugg-text"><strong>Traduci</strong><span>Italiano \u2192 Inglese</span></div>
          </button>
          <button class="suggestion" data-prompt="creami una citta metropolitana al tramonto">
            <div class="sugg-icon">\ud83c\udfa8</div>
            <div class="sugg-text"><strong>Genera un'immagine</strong><span>Citta al tramonto</span></div>
          </button>
        </div>
      </div>
    `;
    attachSuggestionHandlers();
    return;
  }

  container.innerHTML = "";
  const inner = document.createElement("div");
  inner.className = "messages-inner";
  container.appendChild(inner);

  for (const msg of state.messages) {
    inner.appendChild(renderMessage(msg));
  }

  container.scrollTop = container.scrollHeight;
}

function renderMessage(msg) {
  const div = document.createElement("div");
  div.className = `message ${msg.role}${msg.error ? " error" : ""}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = msg.role === "user" ? "U" : (msg.avatar || "\ud83c\udfbc");

  const content = document.createElement("div");
  content.className = "message-content";

  const author = document.createElement("div");
  author.className = "message-author";
  author.innerHTML = `<span>${msg.role === "user" ? "Tu" : (msg.author || "Sinfonia")}</span>`;
  if (msg.meta) {
    author.innerHTML += `<span class="author-meta">${escapeHtml(msg.meta)}</span>`;
  }
  content.appendChild(author);

  const body = document.createElement("div");
  body.className = "message-body";

  if (msg.content) {
    if (msg.rawHtml) {
      body.innerHTML = msg.content;
    } else if (msg.typing) {
      body.innerHTML = `<span class="thinking"><span class="thinking-dots"><span></span><span></span><span></span></span></span>`;
    } else {
      renderContent(body, msg.content);
    }
  } else if (msg.typing) {
    body.innerHTML = `<span class="thinking"><span class="thinking-dots"><span></span><span></span><span></span></span></span>`;
  }

  content.appendChild(body);

  if (msg.role === "assistant" && msg.content && !msg.typing) {
    const actions = document.createElement("div");
    actions.className = "message-actions";
    actions.innerHTML = `<button class="msg-action" onclick="copyMessage(this)">Copia</button>`;
    content.appendChild(actions);
  }

  div.appendChild(avatar);
  div.appendChild(content);
  return div;
}

window.copyMessage = function(btn) {
  const body = btn.closest(".message-content").querySelector(".message-body");
  navigator.clipboard.writeText(body.innerText).then(() => {
    toast("Copiato negli appunti", "success", 1500);
  });
};

/* ---------- Conversazioni ---------- */
function renderConversations() {
  const container = $("#conversations");
  if (!container) return;
  container.innerHTML = "";

  let filtered = state.conversations;
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    filtered = state.conversations.filter(c => (c.title || "").toLowerCase().includes(q));
  }

  if (filtered.length === 0 && state.searchQuery) {
    container.innerHTML = `<div style="padding:20px;text-align:center;font-size:12px;color:var(--text-tertiary);">Nessun risultato</div>`;
    return;
  }

  for (const c of filtered) {
    const div = document.createElement("div");
    div.className = "conv-item" + (c.id === state.currentId ? " active" : "");
    div.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;opacity:0.6;">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
      <span class="conv-title">${escapeHtml(c.title || "Nuova chat")}</span>
      <button class="conv-delete" onclick="event.stopPropagation();deleteConversation('${c.id}')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/>
          <path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/>
        </svg>
      </button>
    `;
    div.onclick = () => loadConversation(c.id);
    container.appendChild(div);
  }
}

window.deleteConversation = function(id) {
  state.conversations = state.conversations.filter(c => c.id !== id);
  if (state.currentId === id) {
    state.currentId = null;
    state.messages = [];
    renderMessages();
  }
  localStorage.setItem("sinfonia.conversations", JSON.stringify(state.conversations));
  renderConversations();
  toast("Conversazione eliminata", "info", 1500);
};

function saveConversation() {
  if (state.messages.length === 0) return;
  const firstUser = state.messages.find(m => m.role === "user");
  const title = firstUser ? firstUser.content.slice(0, 40) : "Nuova chat";
  const existing = state.conversations.find(c => c.id === state.currentId);
  if (existing) {
    existing.title = title;
    existing.messages = state.messages.map(m => ({ ...m, typing: false }));
  } else if (state.currentId) {
    state.conversations.unshift({
      id: state.currentId,
      title,
      messages: state.messages.map(m => ({ ...m, typing: false })),
      timestamp: Date.now(),
    });
  }
  localStorage.setItem("sinfonia.conversations", JSON.stringify(state.conversations));
  renderConversations();
}

function loadConversation(id) {
  const conv = state.conversations.find(c => c.id === id);
  if (!conv) return;
  state.currentId = id;
  state.messages = conv.messages.map(m => ({ ...m, typing: false }));
  renderMessages();
  renderConversations();
  if (window.innerWidth <= 768) closeSidebar();
}

function newChat() {
  state.currentId = null;
  state.messages = [];
  renderMessages();
  renderConversations();
  const inp = $("#input");
  if (inp) inp.focus();
  if (window.innerWidth <= 768) closeSidebar();
}

/* ---------- Sidebar ---------- */
function toggleSidebar() {
  const sidebar = $("#sidebar");
  const overlay = $("#sidebar-overlay");
  if (window.innerWidth <= 768) {
    sidebar.classList.toggle("open");
    overlay.classList.toggle("visible");
  } else {
    sidebar.classList.toggle("collapsed");
    localStorage.setItem("sinfonia.sidebar", sidebar.classList.contains("collapsed") ? "closed" : "open");
  }
}

function closeSidebar() {
  const s = $("#sidebar");
  const o = $("#sidebar-overlay");
  if (s) s.classList.remove("open");
  if (o) o.classList.remove("visible");
}

/* ---------- Intent ---------- */
function detectIntent(text) {
  const msg = text.toLowerCase();
  if (/^(creami|disegna|disegnami|genera|generami|crea|illustra|illustrami)\s/.test(msg)) {
    if (/(video|animazione|clip|filmato)/.test(msg)) return "video";
    if (/(canzone|musica|melodia|brano)/.test(msg)) return "music";
    if (/(traduci|translate)/.test(msg)) return "translation";
    return "image";
  }
  if (/(video|animazione|clip|filmato)/.test(msg)) return "video";
  if (/(canzone|musica|melodia|componi|song|music)/.test(msg)) return "music";
  if (/(traduci|translate|in inglese|in francese|in spagnolo|traduzione)/.test(msg)) return "translation";
  return "text";
}

/* ---------- Multimodal ---------- */
async function generateMultimodal(text, intent) {
  if (intent === "image") {
    const data = await api("/v1/images/generations", {
      method: "POST",
      body: JSON.stringify({ prompt: text }),
    });
    const url = data.url || `data:image/png;base64,${data.b64_data}`;
    return {
      content: `
        <div class="generated-image">
          <div class="img-loading">
            <div class="spinner"></div>
            <div>Generazione immagine in corso...</div>
            <div style="font-size:11px;margin-top:4px;color:var(--text-muted);">${data.provider} \u00b7 ${data.width}x${data.height}</div>
          </div>
          <img src="${url}" alt="${escapeHtml(data.prompt)}" style="display:none;" onload="this.style.display='block';this.previousElementSibling.style.display='none';">
          <div class="img-overlay">
            <span style="color:white;font-size:12px;">${escapeHtml(data.prompt)}</span>
            <a class="img-action" href="${url}" target="_blank">Apri</a>
          </div>
        </div>
      `,
      meta: `${data.provider} \u00b7 ${data.width}x${data.height}`,
      author: `Immagine \u00b7 ${data.provider}`,
      avatar: "\ud83c\udfa8",
      rawHtml: true,
    };
  }
  if (intent === "video") {
    const data = await api("/v1/videos", {
      method: "POST",
      body: JSON.stringify({ prompt: text }),
    });
    return {
      content: `<div style="padding:20px;background:var(--bg-secondary);border-radius:12px;"><div class="thinking">Video in generazione... (job ${data.job_id || "n/a"})</div></div>`,
      meta: `video \u00b7 job ${data.job_id}`,
      author: "Video",
      avatar: "\ud83c\udfac",
      rawHtml: true,
    };
  }
  if (intent === "music") {
    const data = await api("/v1/audio/generations", {
      method: "POST",
      body: JSON.stringify({ prompt: text }),
    });
    return {
      content: `<div style="padding:16px;background:var(--bg-secondary);border-radius:12px;"><audio controls src="${data.url || ""}" style="width:100%;"></audio><div style="font-size:11px;color:var(--text-tertiary);margin-top:8px;">Job: ${data.job_id}</div></div>`,
      meta: `music \u00b7 ${data.job_id}`,
      author: "Musica",
      avatar: "\ud83c\udfb5",
      rawHtml: true,
    };
  }
  return null;
}

/* ---------- Send ---------- */
async function sendMessage(text) {
  if (state.isGenerating) return;
  state.isGenerating = true;
  const sendBtn = $("#send");
  if (sendBtn) sendBtn.disabled = true;

  clearProvider();
  state.messages.push({ role: "user", content: text });
  renderMessages();

  const inp = $("#input");
  if (inp) { inp.value = ""; inp.style.height = "auto"; }

  const intent = detectIntent(text);

  if (intent !== "text") {
    const placeholder = { role: "assistant", content: "", typing: true, avatar: "\ud83c\udfa8" };
    state.messages.push(placeholder);
    renderMessages();

    try {
      const result = await generateMultimodal(text, intent);
      if (result) {
        placeholder.content = result.content;
        placeholder.meta = result.meta;
        placeholder.author = result.author;
        placeholder.avatar = result.avatar;
        placeholder.rawHtml = result.rawHtml;
        placeholder.typing = false;
      } else {
        placeholder.typing = false;
        placeholder.content = "Non riesco a generare questo contenuto.";
      }
    } catch (e) {
      placeholder.typing = false;
      placeholder.content = `Errore: ${e.message}`;
      placeholder.error = true;
      toast(e.message, "error");
    } finally {
      renderMessages();
      saveConversation();
      state.isGenerating = false;
      if (sendBtn) sendBtn.disabled = false;
      if (inp) inp.focus();
    }
    return;
  }

  const placeholder = { role: "assistant", content: "", typing: true };
  state.messages.push(placeholder);
  renderMessages();

  const t0 = Date.now();

  try {
    let data;
    if (state.ensemble) {
      data = await api("/v1/ensemble", {
        method: "POST",
        body: JSON.stringify({ messages: [{ role: "user", content: text }] }),
      });
      placeholder.content = data.final_content;
      placeholder.meta = `ensemble \u00b7 ${data.successful_panels}/${data.total_panels} panel`;
      placeholder.author = `Ensemble (${data.judge_model})`;
      placeholder.avatar = "\ud83c\udfbc";
      showProvider(`ensemble (${data.successful_panels} AI + giudice)`, data.total_tokens, ((Date.now() - t0) / 1000).toFixed(1));
    } else {
      const payload = { model: state.currentModel, messages: [{ role: "user", content: text }] };
      if (state.currentId) payload.conversation_id = state.currentId;
      data = await api("/v1/chat/completions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      placeholder.content = data.choices[0].message.content;
      state.currentId = data.conversation_id || state.currentId;
      const provider = (data.model || "").replace("sinfonia/", "");
      const tokens = (data.usage && data.usage.total_tokens) || 0;
      placeholder.meta = `${provider} \u00b7 ${tokens} token`;
      placeholder.author = provider.split("/")[0] || "Sinfonia";
      showProvider(provider, tokens, ((Date.now() - t0) / 1000).toFixed(1));
    }
    placeholder.typing = false;
    renderMessages();
    saveConversation();
  } catch (e) {
    placeholder.typing = false;
    placeholder.content = `Errore: ${e.message}`;
    placeholder.error = true;
    renderMessages();
    toast(e.message, "error");
  } finally {
    state.isGenerating = false;
    if (sendBtn) sendBtn.disabled = false;
    if (inp) inp.focus();
  }
}

/* ---------- Suggestions ---------- */
function attachSuggestionHandlers() {
  document.querySelectorAll(".suggestion").forEach(btn => {
    btn.onclick = () => {
      const prompt = btn.getAttribute("data-prompt");
      if (prompt) sendMessage(prompt);
    };
  });
}

/* ---------- Theme ---------- */
function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  localStorage.setItem("sinfonia.theme", next);
  mermaidReady = false;
  initMermaid();
}

/* ---------- Init ---------- */
function init() {
  const savedTheme = localStorage.getItem("sinfonia.theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);

  if (localStorage.getItem("sinfonia.sidebar") === "closed" && window.innerWidth > 768) {
    $("#sidebar").classList.add("collapsed");
  }

  try {
    const saved = localStorage.getItem("sinfonia.conversations");
    if (saved) state.conversations = JSON.parse(saved);
  } catch (e) {}

  renderConversations();
  renderMessages();
  initMermaid();
  checkHealth();
  loadModels();
  loadCredits();
  setInterval(loadCredits, 30000);
  setInterval(checkHealth, 30000);

  $("#new-chat").onclick = newChat;
  $("#toggle-sidebar").onclick = toggleSidebar;
  $("#menu-btn").onclick = () => {
    $("#sidebar").classList.add("open");
    $("#sidebar-overlay").classList.add("visible");
  };
  $("#sidebar-overlay").onclick = closeSidebar;
  $("#theme-btn").onclick = toggleTheme;

  $("#model-btn").onclick = (e) => {
    e.stopPropagation();
    $("#model-dropdown").classList.toggle("open");
  };
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".model-picker")) {
      const dd = $("#model-dropdown");
      if (dd) dd.classList.remove("open");
    }
  });

  $("#ensemble-toggle").onclick = () => {
    state.ensemble = !state.ensemble;
    $("#ensemble-toggle").classList.toggle("active", state.ensemble);
    if (state.ensemble) toast("Modalit\u00e0 Ensemble attiva", "info", 2000);
  };

  $("#toggle-credits").onclick = () => {
    $("#toggle-credits").classList.toggle("closed");
    $("#credits-list").classList.toggle("closed");
  };

  $("#search-conv").addEventListener("input", (e) => {
    state.searchQuery = e.target.value;
    renderConversations();
  });

  $("#composer").onsubmit = (e) => {
    e.preventDefault();
    const text = $("#input").value.trim();
    if (!text) return;
    sendMessage(text);
  };

  const input = $("#input");
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 200) + "px";
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("#composer").requestSubmit();
    }
  });

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      newChat();
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 768) closeSidebar();
  });
}

document.addEventListener("DOMContentLoaded", init);
