/* ============================================================
   BRO — Voce nativa browser
   Wake word "Ehi Doc" + STT + TTS, tutto lato client.
   ============================================================ */
(function() {
  let recognition = null;
  let isActivated = false;
  let conversationTimer = null;
  const WAKE_WORDS = ["ehi doc", "ei doc", "hey doc", "ehi bro", "ei bro", "hey bro", "ok doc", "ok bro", "ehi sinfonia"];

  const $ = (sel) => document.querySelector(sel);

  function setVoiceStatus(text, cls) {
    const el = $("#voice-status");
    if (!el) return;
    if (!text) { el.classList.remove("visible", "transcribing", "speaking"); el.textContent = ""; return; }
    el.classList.add("visible");
    el.classList.remove("transcribing", "speaking");
    if (cls) el.classList.add(cls);
    el.textContent = text;
  }

  function updateMicButton(active) {
    const btn = $("#voice-toggle");
    if (!btn) return;
    btn.classList.toggle("active", active);
    const label = btn.querySelector(".mic-label");
    if (label) label.textContent = active ? "Voce attiva" : "Attiva voce";
  }

  function setFaceMood(mood) { /* rimosso */ }

  // === Pannello trascrizione ===
  function showTranscriptPanel() {
    const p = $("#transcript-panel");
    if (p) p.classList.add("visible");
  }

  function addTranscript(text, type) {
    const list = $("#transcript-list");
    if (!list) return;
    const time = new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    const item = document.createElement("div");
    item.className = "transcript-item";
    item.innerHTML = '<span class="time">' + time + '</span>' + escapeHtml(text);
    if (type === "user") item.style.color = "#00ff88";
    list.appendChild(item);
    list.scrollTop = list.scrollHeight;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
  }

  // === TTS ===
  function speak(text) {
    if (!("speechSynthesis" in window)) {
      console.warn("SpeechSynthesis non supportato");
      return;
    }
    window.speechSynthesis.cancel();
    text = text.replace(/```[\s\S]*?```/g, "")
      .replace(/`[^`]+`/g, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/^#+\s*/gm, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/\|/g, "")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) return;
    if (text.length > 1000) text = text.slice(0, 1000) + "...";

    const utter = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();
    const italian = voices.find(v => v.lang.startsWith("it"));
    if (italian) utter.voice = italian;
    utter.lang = "it-IT";
    utter.rate = 1.0;
    utter.onstart = () => {  setVoiceStatus("🔊 Sto parlando", "speaking"); };
    utter.onend = () => { setVoiceStatus("🎤 In ascolto — di' 'Ehi Doc'", null);  };
    utter.onerror = () => { setVoiceStatus("", null);  };
    window.speechSynthesis.speak(utter);
  }

  // === STT ===
  function initRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;
    const rec = new SR();
    rec.lang = "it-IT";
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      setVoiceStatus("🎤 In ascolto — di' 'Ehi Doc'", null);
      
    };

    rec.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript.trim();
        if (event.results[i].isFinal) {
          handleFinalTranscript(transcript);
        } else {
          interim += transcript + " ";
        }
      }
      if (interim) {
        setVoiceStatus("🎤 Sto sentendo: \"" + interim.trim() + "\"", null);
      }
    };

    rec.onerror = (event) => {
      if (event.error === "no-speech" || event.error === "aborted") return;
      if (event.error === "not-allowed") {
        setVoiceStatus("❌ Permesso microfono negato", null);
        deactivate();
        return;
      }
      console.error("SR error:", event.error);
    };

    rec.onend = () => {
      if (isActivated) setTimeout(() => { if (isActivated) try { rec.start(); } catch(e){} }, 200);
    };

    return rec;
  }

  let lastWakeTime = 0;
  let bufferAfterWake = "";
  let waitingForCommand = false;

  function handleFinalTranscript(transcript) {
    const lower = transcript.toLowerCase();
    const now = Date.now();

    // Fase 1: cerca wake word
    if (!waitingForCommand) {
      for (const wake of WAKE_WORDS) {
        if (lower.includes(wake)) {
          lastWakeTime = now;
          waitingForCommand = true;
          const after = lower.split(wake)[1]?.trim() || "";
          bufferAfterWake = after;
          setVoiceStatus("🎤 Ti ascolto...", null);
          
          clearTimeout(conversationTimer);
          conversationTimer = setTimeout(() => {
            if (bufferAfterWake.trim()) {
              const q = bufferAfterWake.trim();
              bufferAfterWake = ""; waitingForCommand = false;
              sendToSinfonia(q);
            } else {
              waitingForCommand = false;
              setVoiceStatus("🎤 In ascolto — di' 'Ehi Doc'", null);
            }
          }, 5000);
          return;
        }
      }
      return;
    }

    // Fase 2: aspetto la domanda
    bufferAfterWake = (bufferAfterWake + " " + transcript).trim();
    clearTimeout(conversationTimer);
    conversationTimer = setTimeout(() => {
      if (bufferAfterWake.trim()) {
        const q = bufferAfterWake.trim();
        bufferAfterWake = ""; waitingForCommand = false;
        sendToSinfonia(q);
      }
    }, 2500);
  }

  async function sendToSinfonia(text) {
    setVoiceStatus("🧠 Elaboro: \"" + text + "\"", "transcribing");
    
    addTranscript("👤 " + text, "user");

    // Mostra messaggio utente nella chat
    if (window.state && window.renderMessages) {
      window.state.messages.push({ role: "user", content: text });
      window.renderMessages();
    }

    try {
      // Chiamata DIRETTA con voice_mode: true
      const payload = {
        model: "sinfonia/auto",
        messages: [{ role: "user", content: text }],
        voice_mode: true,
      };

      const res = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const response = data.choices[0].message.content;

      // Aggiungi risposta alla chat
      if (window.state && window.renderMessages) {
        window.state.messages.push({ role: "assistant", content: response });
        window.renderMessages();
      }

      // Aggiungi alla trascrizione
      addTranscript("🤖 " + response.substring(0, 200) + (response.length > 200 ? "..." : ""), "assistant");

      // Parla
      speak(response);
    } catch (e) {
      console.error("Errore invio:", e);
      setVoiceStatus("❌ Errore: " + e.message, null);
      setTimeout(() => setVoiceStatus("", null), 3000);
    }
  }

  async function activate() {
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setVoiceStatus("❌ Permesso microfono negato. Abilitalo nelle impostazioni del browser.", null);
      return;
    }
    isActivated = true;
    updateMicButton(true);
    showTranscriptPanel();

    if (!recognition) recognition = initRecognition();
    if (!recognition) {
      setVoiceStatus("❌ Browser non supporta voce. Usa Chrome/Edge.", null);
      return;
    }
    try { recognition.start(); } catch(e) { console.warn(e); }
  }

  function deactivate() {
    isActivated = false;
    updateMicButton(false);
    if (recognition) try { recognition.stop(); } catch(e) {}
    setVoiceStatus("", null);
    
  }

  function initVoiceUI() {
    const btn = $("#voice-toggle");
    if (btn) btn.onclick = () => isActivated ? deactivate() : activate();

    const clearBtn = $("#transcript-clear");
    if (clearBtn) clearBtn.onclick = () => {
      const list = $("#transcript-list");
      if (list) list.innerHTML = "";
    };

    if ("speechSynthesis" in window) {
      window.speechSynthesis.getVoices();
      window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
    }
    console.log("OK: voice UI pronta");
  }

  window.BroVoiceUI = { activate, deactivate, speak, isActive: () => isActivated };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initVoiceUI);
  } else {
    initVoiceUI();
  }
})();
