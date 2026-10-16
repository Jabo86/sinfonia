/* SINFONIA — APP 2026 */
const API = "";
const state = {
  conversations: [], currentId: null, messages: [],
  currentModel: "sinfonia/auto", isGenerating: false,
  searchQuery: "",
};
const $ = (sel) => document.querySelector(sel);

async function api(path, opts = {}) {
  const res = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

function toast(message, type = "info", duration = 3000) {
  const c = $("#toast-container"); if (!c) return;
  const el = document.createElement("div");
  el.className = "toast" + (type === "error" ? " error" : "");
  el.textContent = message;
  c.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

async function checkHealth() {
  const dot = $("#status-pill .status-dot");
  const txt = $("#status-text");
  try {
    const data = await api("/health");
    if (dot) dot.className = "status-dot ok";
    if (txt) txt.textContent = data.free_providers + " NODI ONLINE";
  } catch (e) {
    if (dot) dot.className = "status-dot err";
    if (txt) txt.textContent = "OFFLINE";
  }
}

async function loadCredits() {
  try {
    const data = await api("/v1/credits");
    const c = $("#credits-list"); if (!c) return;
    c.innerHTML = "";
    for (const [pid, info] of Object.entries(data)) {
      if (info.type !== "free") continue;
      const div = document.createElement("div");
      div.className = "credit-item";
      const dotClass = info.available ? "ok" : "err";
      const value = info.rpd_limit ? (info.rpd_used + "/" + info.rpd_limit) : "" + info.rpd_used;
      div.innerHTML = '<span class="credit-dot ' + dotClass + '"></span><span class="credit-name">' + escapeHtml(info.name) + '</span><span class="credit-value">' + value + '</span>';
      c.appendChild(div);
    }
  } catch (e) {}
}

function addMessage(role, content, meta) {
  state.messages.push({ role: role, content: content, meta: meta || null, error: false });
  renderMessages();
}

function renderMessages() {
  const container = $("#messages"); if (!container) return;
  if (state.messages.length === 0) { container.innerHTML = ""; return; }
  container.innerHTML = "";
  for (const m of state.messages) {
    const div = document.createElement("div");
    div.className = "msg " + m.role + (m.error ? " error" : "");
    const body = document.createElement("div");
    body.className = "msg-body";
    if (m.content) {
      if (typeof marked !== "undefined") body.innerHTML = marked.parse(m.content);
      else body.textContent = m.content;
      if (typeof renderMathInElement !== "undefined") {
        try { renderMathInElement(body, { delimiters: [{left:"$$",right:"$$",display:true},{left:"$",right:"$",display:false}], throwOnError: false }); } catch(e) {}
      }
    } else { body.textContent = "..."; }
    div.appendChild(body);
    container.appendChild(div);
  }
  container.scrollTop = container.scrollHeight;
}

async function sendMessage(text) {
  if (state.isGenerating) return;
  if (!text.trim()) return;

  state.isGenerating = true;
  const send = $("#send"); if (send) send.disabled = true;

  state.messages.push({ role: "user", content: text });
  renderMessages();
  if ($("#input")) { $("#input").value = ""; $("#input").style.height = "auto"; }

  const placeholder = { role: "assistant", content: "" };
  state.messages.push(placeholder);
  renderMessages();

  try {
    const profile = window.BroProfile && window.BroProfile.getCurrentProfile();
    const payload = {
      model: state.currentModel,
      messages: state.messages.filter(m => m.content).map(m => ({ role: m.role, content: m.content })),
      profession: profile ? profile.profession : null,
    };
    if (state.currentId) payload.conversation_id = state.currentId;

    const data = await api("/v1/chat/completions", { method: "POST", body: JSON.stringify(payload) });
    placeholder.content = data.choices[0].message.content;
    state.currentId = data.conversation_id || state.currentId;
    renderMessages();
    saveConversation();
  } catch (e) {
    placeholder.content = "Errore: " + e.message;
    placeholder.error = true;
    renderMessages();
  } finally {
    state.isGenerating = false;
    if (send) send.disabled = false;
    if ($("#input")) $("#input").focus();
  }
}

function saveConversation() {
  if (state.messages.length === 0) return;
  const firstUser = state.messages.find(m => m.role === "user");
  const title = firstUser ? firstUser.content.slice(0, 40) : "Sessione";
  const existing = state.conversations.find(c => c.id === state.currentId);
  if (existing) existing.messages = [...state.messages];
  else if (state.currentId) state.conversations.unshift({ id: state.currentId, title: title, messages: [...state.messages] });
  localStorage.setItem("sinfonia.conversations", JSON.stringify(state.conversations));
  renderConversations();
}

function renderConversations() {
  const c = $("#conversations"); if (!c) return;
  c.innerHTML = "";
  let list = state.conversations;
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    list = list.filter(x => (x.title || "").toLowerCase().includes(q));
  }
  for (const conv of list) {
    const div = document.createElement("div");
    div.className = "conv-item" + (conv.id === state.currentId ? " active" : "");
    div.textContent = conv.title || "Sessione";
    div.onclick = function() {
      state.currentId = conv.id;
      state.messages = [...conv.messages];
      renderMessages();
      renderConversations();
    };
    c.appendChild(div);
  }
}

function newChat() {
  state.currentId = null;
  state.messages = [];
  renderMessages();
  renderConversations();
  if ($("#input")) $("#input").focus();
}

async function loadProfessions() {
  try {
    const res = await fetch("/v1/professions");
    const data = await res.json();
    const professions = data.professions || [];
    renderProfDropdown(professions);
    const profile = window.BroProfile && window.BroProfile.getCurrentProfile();
    if (profile) {
      const match = professions.find(p => p.id === profile.profession);
      if (match) {
        const iconEl = document.getElementById("prof-icon");
        const nameEl = document.getElementById("prof-name");
        if (iconEl) iconEl.textContent = match.icon;
        if (nameEl) nameEl.textContent = match.name;
      }
    }
  } catch (e) {
    console.error("Errore caricamento profili:", e);
  }
}

function renderProfDropdown(professions) {
  const dropdown = document.getElementById("prof-dropdown");
  if (!dropdown) return;
  dropdown.innerHTML = "";
  const currentProfile = window.BroProfile && window.BroProfile.getCurrentProfile();
  const currentId = currentProfile ? currentProfile.profession : "generico";
  for (const p of professions) {
    const opt = document.createElement("div");
    opt.className = "prof-option" + (p.id === currentId ? " active" : "");
    opt.innerHTML = '<span class="prof-opt-icon">' + p.icon + '</span><span class="prof-opt-name">' + p.name + '</span><span class="prof-opt-desc">' + (p.description || "") + '</span>';
    opt.onclick = () => selectProfession(p);
    dropdown.appendChild(opt);
  }
}

function selectProfession(prof) {
  if (window.BroProfile) {
    const current = window.BroProfile.getProfile() || {};
    current.profession = prof.id;
    if (!current.userName) current.userName = "Utente";
    window.BroProfile.saveProfile(current);
  }
  const iconEl = document.getElementById("prof-icon");
  const nameEl = document.getElementById("prof-name");
  if (iconEl) iconEl.textContent = prof.icon;
  if (nameEl) nameEl.textContent = prof.name;
  const dropdown = document.getElementById("prof-dropdown");
  if (dropdown) dropdown.classList.remove("open");
  toast("Profilo: " + prof.icon + " " + prof.name, "success", 2000);
}

function initProfPicker() {
  const btn = document.getElementById("prof-btn");
  const dropdown = document.getElementById("prof-dropdown");
  if (!btn || !dropdown) return;
  btn.onclick = (e) => { e.stopPropagation(); dropdown.classList.toggle("open"); };
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".prof-picker")) dropdown.classList.remove("open");
  });
  loadProfessions();
}

function init() {
  if (window.BroOnboarding && window.BroOnboarding.showIfNeeded()) return;
  const profile = window.BroProfile && window.BroProfile.getCurrentProfile();
  if (profile) {
    if ($("#input")) $("#input").placeholder = "Scrivi un messaggio a Sinfonia...";
    if (state.messages.length === 0 && profile.greeting) {
      state.messages.push({ role: "assistant", content: "**Ehi " + profile.userName + "**, sono **" + profile.assistant + "**. " + profile.greeting });
    }
  }
  try {
    const saved = localStorage.getItem("sinfonia.conversations");
    if (saved) state.conversations = JSON.parse(saved);
  } catch (e) {}
  initProfPicker();
  renderConversations();
  renderMessages();
  checkHealth();
  loadCredits();
  setInterval(checkHealth, 30000);
  setInterval(loadCredits, 30000);
  const sidebar = $("#sidebar");
  const main = $(".main");
  if ($("#menu-btn")) $("#menu-btn").addEventListener("click", function() {
    if (sidebar) sidebar.classList.toggle("collapsed");
    if (main) main.classList.toggle("with-sidebar", !sidebar.classList.contains("collapsed"));
  });
  if ($("#toggle-sidebar")) $("#toggle-sidebar").addEventListener("click", function() {
    if (sidebar) sidebar.classList.add("collapsed");
    if (main) main.classList.remove("with-sidebar");
  });
  if ($("#new-chat")) $("#new-chat").addEventListener("click", newChat);
  if ($("#search-conv")) $("#search-conv").addEventListener("input", function(e) {
    state.searchQuery = e.target.value;
    renderConversations();
  });
  if ($("#composer")) $("#composer").addEventListener("submit", function(e) {
    e.preventDefault();
    const text = $("#input").value.trim();
    if (text) sendMessage(text);
  });
  const input = $("#input");
  if (input) {
    input.addEventListener("input", function() {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 150) + "px";
    });
    input.addEventListener("keydown", function(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        $("#composer").requestSubmit();
      }
    });
  }
  document.addEventListener("keydown", function(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      newChat();
    }
  });
}

document.addEventListener("DOMContentLoaded", init);
window.sendMessage = sendMessage;
window.addMessage = addMessage;
window.renderMessages = renderMessages;
window.state = state;
console.log("OK: app.js pronto");
