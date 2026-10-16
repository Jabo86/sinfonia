/* BRO — APP 2026 */
const API = "";
const state = {
  conversations: [], currentId: null, messages: [],
  currentModel: "sinfonia/auto", isGenerating: false,
  searchQuery: "", _skinKey: "ai",
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

function detectSkinCommand(text) {
  const msg = text.toLowerCase().trim();
  const patterns = [
    /cambia (?:forma|sembianze|aspetto) in (?:un |una |il |la |lo )?(\w+)/,
    /diventa (?:un |una |il |la |lo )?(\w+)/,
    /trasformati in (?:un |una |il |la |lo )?(\w+)/,
    /mostra (?:la tua )?forma (?:di )?(\w+)/,
    /prendi (?:la )?forma (?:di |del |della )?(\w+)/,
  ];
  const aliases = {
    "drago":"dragon","dragon":"dragon","gatto":"cat","gatta":"cat","cat":"cat","felino":"cat",
    "alieno":"alien","aliena":"alien","alien":"alien","umano":"human","umana":"human","human":"human","uomo":"human","donna":"human",
    "fantasma":"ghost","ghost":"ghost","spettro":"ghost","fuoco":"fire","fire":"fire","fiamma":"fire",
    "ai":"ai","robot":"ai","androide":"ai","normale":"ai","default":"ai"
  };
  for (const p of patterns) {
    const m = msg.match(p);
    if (m) {
      const key = m[1].replace(/[^\w]/g, "");
      if (aliases[key]) return aliases[key];
    }
  }
  return null;
}

async function handleSkinCommand(text) {
  const skin = detectSkinCommand(text);
  if (!skin) return false;
  if (window.Face && window.Face.setSkin(skin)) {
    // Aspetta un frame per permettere al canvas di aggiornarsi
    await new Promise(r => setTimeout(r, 50));
    const name = window.Face.getSkinName();
    if ($("#face-name")) $("#face-name").textContent = name;
    if ($("#skin-name")) $("#skin-name").textContent = name;
    
    setTimeout(() => window.Face.setMood("idle"), 2500);
    toast("Forma: " + name, "info", 2000);
    return true;
  }
  return false;
}


function addMessage(role, content, meta) {
  state.messages.push({ role: role, content: content, meta: meta || null, error: false });
  renderMessages();
}

function renderMessages() {
  const container = $("#messages"); if (!container) return;
  if (state.messages.length === 0) { container.innerHTML = ""; return; }
  container.innerHTML = "";
  const inner = document.createElement("div");
  inner.className = "messages-inner";
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
    } else { body.textContent = "···"; }
    div.appendChild(body);
    inner.appendChild(div);
  }
  container.appendChild(inner);
  container.scrollTop = container.scrollHeight;
}

async function sendMessage(text) {
  if (state.isGenerating) return;
  if (!text.trim()) return;
  const isSkin = await handleSkinCommand(text);
  if (isSkin) {
    state.messages.push({ role: "user", content: text });
    state.messages.push({ role: "assistant", content: "Forma cambiata in **" + window.Face.getSkinName() + "**." });
    renderMessages();
    saveConversation();
    if ($("#input")) $("#input").value = "";
    return;
  }
  state.isGenerating = true;
  const send = $("#send"); if (send) send.disabled = true;
  
  state.messages.push({ role: "user", content: text });
  renderMessages();
  if ($("#input")) { $("#input").value = ""; $("#input").style.height = "auto"; }
  const placeholder = { role: "assistant", content: "" };
  state.messages.push(placeholder);
  renderMessages();
  try {
    const payload = {
      model: state.currentModel,
        profession: (window.BroProfile && window.BroProfile.getCurrentProfile()) ? window.BroProfile.getCurrentProfile().profession : null,
      messages: state.messages.filter(m => m.content).map(m => ({ role: m.role, content: m.content })),
    };
    if (state.currentId) payload.conversation_id = state.currentId;
    const data = await api("/v1/chat/completions", { method: "POST", body: JSON.stringify(payload) });
    placeholder.content = data.choices[0].message.content;
    state.currentId = data.conversation_id || state.currentId;
    if (window.Face) {  setTimeout(() => window.Face.setMood("idle"), 2000); }
    renderMessages();
    saveConversation();
  } catch (e) {
    placeholder.content = "Errore: " + e.message;
    placeholder.error = true;
    if (window.Face) {  setTimeout(() => window.Face.setMood("idle"), 2000); }
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
  localStorage.setItem("bro.conversations", JSON.stringify(state.conversations));
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


/* ============================================================
   SELETTORE PROFILO
   ============================================================ */
async function loadProfessions() {
  try {
    const res = await fetch("/v1/professions");
    const data = await res.json();
    const professions = data.professions || [];
    renderProfDropdown(professions);
    // Applica il profilo corrente
    const profile = window.BroProfile && window.BroProfile.getCurrentProfile();
    if (profile) {
      const match = professions.find(p => p.id === profile.profession);
      if (match) {
        document.getElementById("prof-icon").textContent = match.icon;
        document.getElementById("prof-name").textContent = match.name;
      }
    }
  } catch (e) {
    console.error("Errore caricamento profili:", e);
  }
}

let _professionsCache = [];

function renderProfDropdown(professions) {
  _professionsCache = professions;
  const dropdown = document.getElementById("prof-dropdown");
  if (!dropdown) return;
  dropdown.innerHTML = "";

  const currentProfile = window.BroProfile && window.BroProfile.getCurrentProfile();
  const currentId = currentProfile ? currentProfile.profession : "generico";

  for (const p of professions) {
    const opt = document.createElement("div");
    opt.className = "prof-option" + (p.id === currentId ? " active" : "");
    opt.innerHTML = `
      <span class="prof-opt-icon">${p.icon}</span>
      <span class="prof-opt-name">${p.name}</span>
      <span class="prof-opt-desc">${p.description || ""}</span>
    `;
    opt.onclick = () => selectProfession(p);
    dropdown.appendChild(opt);
  }
}

function selectProfession(prof) {
  // Salva nel profilo utente
  if (window.BroProfile) {
    const current = window.BroProfile.getProfile() || {};
    current.profession = prof.id;
    if (!current.userName) current.userName = "Utente";
    window.BroProfile.saveProfile(current);
  }

  // Aggiorna UI
  document.getElementById("prof-icon").textContent = prof.icon;
  document.getElementById("prof-name").textContent = prof.name;
  document.getElementById("prof-dropdown").classList.remove("open");

  // Aggiorna anche la skin per coerenza visiva
  const skinMap = {
    generico: "ai",
    medico: "human",
    avvocato: "human",
    programmatore: "ai",
    insegnante: "human",
    artigiano: "ai",
    commercialista: "human",
    ricercatore: "alien",
    cuoco: "fire",
    musicista: "ghost",
  };
  if (window.Face && skinMap[prof.id]) {
    
  }

  // Aggiorna anche il nome assistente (Doc, Dev, ecc.)
  const logoText = document.querySelector(".logo-text");
  if (logoText) logoText.textContent = prof.name.toUpperCase();

  const faceName = document.getElementById("face-name");
  if (faceName) faceName.textContent = prof.name;

  toast(`Profilo: ${prof.icon} ${prof.name}`, "success", 2000);
}

function initProfPicker() {
  const btn = document.getElementById("prof-btn");
  const dropdown = document.getElementById("prof-dropdown");
  if (!btn || !dropdown) return;

  btn.onclick = (e) => {
    e.stopPropagation();
    dropdown.classList.toggle("open");
  };

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".prof-picker")) {
      dropdown.classList.remove("open");
    }
  });

  loadProfessions();
}

function init() {
  if (window.BroOnboarding && window.BroOnboarding.showIfNeeded()) return;

  const profile = window.BroProfile.getCurrentProfile();
  if (profile) {
    if (document.querySelector(".logo-text")) document.querySelector(".logo-text").textContent = profile.assistant.toUpperCase();
    if (document.querySelector(".topbar-title")) document.querySelector(".topbar-title").textContent = profile.assistant.toUpperCase() + " // " + profile.userName;
    if ($("#face-name")) $("#face-name").textContent = profile.assistant;
    if ($("#skin-name")) $("#skin-name").textContent = profile.assistant;
    if (window.Face && profile.skin) 
    if ($("#input")) $("#input").placeholder = "Parla con " + profile.assistant + "...";
    if (state.messages.length === 0 && profile.greeting) {
      state.messages.push({ role: "assistant", content: "**Ehi " + profile.userName + "**, sono **" + profile.assistant + "**. " + profile.greeting });
    }
    const footer = document.querySelector(".sidebar-footer");
    if (footer && !document.querySelector(".change-profile-btn")) {
      const btn = document.createElement("button");
      btn.className = "change-profile-btn";
      btn.textContent = "🔄 Cambia profilo";
      btn.onclick = function() {
        if (confirm("Vuoi riconfigurare il tuo profilo?")) {
          window.BroProfile.clearProfile();
          localStorage.removeItem("bro.conversations");
          window.location.reload();
        }
      };
      footer.parentNode.insertBefore(btn, footer);
    }
  }

  try {
    const saved = localStorage.getItem("bro.conversations");
    if (saved) state.conversations = JSON.parse(saved);
  } catch (e) {}

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

  if ($("#skin-btn")) $("#skin-btn").addEventListener("click", function() {
    if (!window.Face) return;
    const skins = window.Face.listSkins();
    const currentKey = state._skinKey || skins[0];
    const idx = skins.indexOf(currentKey);
    const next = skins[(idx + 1) % skins.length];
    state._skinKey = next;
    
    const name = window.Face.getSkinName();
    if ($("#face-name")) $("#face-name").textContent = name;
    if ($("#skin-name")) $("#skin-name").textContent = name;
    toast("Forma: " + name, "info", 1500);
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

/* ============================================================
   VOICE STATE POLLING — Feedback visivo HUD
   ============================================================ */
(function() {
  let lastState = "idle";
  let lastRealState = "idle";

  async function pollVoiceState() {
    try {
      const res = await fetch("/v1/voice/state");
      if (!res.ok) return;
      const data = await res.json();
      const state = data.state || "idle";

      if (state !== lastState) {
        lastState = state;
        applyMood(state);
      }
    } catch (e) {
      // server offline, ignora
    }
  }

  function applyMood(state) {
    if (!window.Face) return;
    let mood = "idle";

    if (state === "recording") mood = "listening";
    else if (state === "transcribing") mood = "thinking";
    else if (state === "thinking") mood = "thinking";
    else if (state === "speaking") mood = "speaking";
    else if (state.startsWith("heard:")) mood = "happy";
    else if (state.startsWith("response:")) mood = "speaking";
    else if (state === "listening") mood = "listening";
    else mood = "idle";

    
    lastRealState = mood;

    // Aggiorna anche il topbar con l'ultima frase sentita
    if (state.startsWith("heard:") && document.querySelector(".topbar-title")) {
      const text = state.substring(6);
      // niente, lasciamo il titolo normale
    }
  }

  setInterval(pollVoiceState, 500);
  pollVoiceState();

  console.log("OK: voice state polling attivo");
})();

/* ============================================================
   ESPOSIZIONE GLOBALE per voice_ui.js
   ============================================================ */
window.sendMessage = sendMessage;
window.addMessage = addMessage;
window.renderMessages = renderMessages;
window.state = state;
console.log("OK: funzioni esposte globalmente");
