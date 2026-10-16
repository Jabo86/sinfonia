/* ============================================================
   JARVIS HUD — Interfaccia olografica fantascientifica
   ============================================================ */
(function() {
  const canvas = document.getElementById("face-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const SIZE = 400;
  canvas.width = SIZE * 2;
  canvas.height = SIZE * 2;
  canvas.style.width = SIZE + "px";
  canvas.style.height = SIZE + "px";
  ctx.scale(2, 2);

  const cx = SIZE / 2;
  const cy = SIZE / 2;

  const state = {
    skin: "ai",
    mood: "idle",       // idle | thinking | speaking | listening | happy | error
    time: 0,
    rings: [],
    particles: [],
    waveform: new Array(64).fill(0),
    waveformTargets: new Array(64).fill(0),
    corePulse: 0,
    scanAngle: 0,
    dataStream: [],
    bootedAt: Date.now(),
  };

  const SKINS = {
    ai: {
      name: "AI",
      primary: "#00ff88",
      secondary: "#00ccff",
      accent: "#aaffee",
      glow: "rgba(0, 255, 136, 0.6)",
      bg: "rgba(0, 30, 15, 0.4)",
      coreInner: "#ffffff",
      coreOuter: "#00ff88",
    },
    dragon: {
      name: "Drago",
      primary: "#ff4400",
      secondary: "#ffcc00",
      accent: "#ffee88",
      glow: "rgba(255, 100, 0, 0.6)",
      bg: "rgba(40, 10, 0, 0.4)",
      coreInner: "#ffffff",
      coreOuter: "#ff4400",
    },
    cat: {
      name: "Gatto",
      primary: "#ffaa44",
      secondary: "#ffdd88",
      accent: "#ffffff",
      glow: "rgba(255, 170, 68, 0.6)",
      bg: "rgba(30, 20, 5, 0.4)",
      coreInner: "#ffffff",
      coreOuter: "#ffaa44",
    },
    alien: {
      name: "Alieno",
      primary: "#cc44ff",
      secondary: "#44ffcc",
      accent: "#ffffff",
      glow: "rgba(200, 68, 255, 0.6)",
      bg: "rgba(20, 5, 30, 0.4)",
      coreInner: "#ffffff",
      coreOuter: "#cc44ff",
    },
    human: {
      name: "Umano",
      primary: "#88ccff",
      secondary: "#ffffff",
      accent: "#aaddff",
      glow: "rgba(136, 204, 255, 0.6)",
      bg: "rgba(5, 15, 30, 0.4)",
      coreInner: "#ffffff",
      coreOuter: "#88ccff",
    },
    ghost: {
      name: "Fantasma",
      primary: "#aaccff",
      secondary: "#ffffff",
      accent: "#ddeeff",
      glow: "rgba(170, 204, 255, 0.5)",
      bg: "rgba(15, 15, 30, 0.3)",
      coreInner: "#ffffff",
      coreOuter: "#aaccff",
    },
    fire: {
      name: "Fuoco",
      primary: "#ff6600",
      secondary: "#ffcc00",
      accent: "#ffff88",
      glow: "rgba(255, 102, 0, 0.6)",
      bg: "rgba(30, 10, 0, 0.4)",
      coreInner: "#ffffff",
      coreOuter: "#ff6600",
    },
  };

  // === INIT RINGS ===
  function initRings() {
    state.rings = [
      { r: 160, speed:  0.008, segments: 60, thickness: 1.5, alpha: 0.5, dir:  1, dotted: false },
      { r: 140, speed: -0.012, segments: 12, thickness: 3,   alpha: 0.7, dir: -1, dotted: false },
      { r: 115, speed:  0.018, segments: 48, thickness: 1,   alpha: 0.4, dir:  1, dotted: true  },
      { r:  95, speed: -0.025, segments:  8, thickness: 4,   alpha: 0.9, dir: -1, dotted: false },
      { r:  75, speed:  0.035, segments: 32, thickness: 2,   alpha: 0.8, dir:  1, dotted: false },
      { r:  55, speed: -0.045, segments: 16, thickness: 1.5, alpha: 0.6, dir: -1, dotted: true  },
    ];
    for (const ring of state.rings) {
      ring.angle = Math.random() * Math.PI * 2;
    }
  }

  // === INIT PARTICLES ===
  function initParticles() {
    state.particles = [];
    for (let i = 0; i < 40; i++) {
      state.particles.push({
        angle: Math.random() * Math.PI * 2,
        radius: 60 + Math.random() * 130,
        speed: (Math.random() - 0.5) * 0.02,
        size: 0.5 + Math.random() * 1.5,
        alpha: 0.3 + Math.random() * 0.7,
        pulse: Math.random() * Math.PI * 2,
      });
    }
  }

  // === INIT DATA STREAM ===
  function initDataStream() {
    state.dataStream = [];
    for (let i = 0; i < 8; i++) {
      state.dataStream.push({
        y: Math.random() * SIZE,
        speed: 0.5 + Math.random() * 1.5,
        text: Math.random().toString(16).substring(2, 8).toUpperCase(),
        side: i % 2 === 0 ? "left" : "right",
      });
    }
  }

  // === DRAW RING ===
  function drawRing(ring, skin) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(ring.angle);

    ctx.strokeStyle = skin.primary;
    ctx.shadowColor = skin.glow;
    ctx.shadowBlur = 15;
    ctx.lineWidth = ring.thickness;

    if (ring.dotted) {
      // Anello tratteggiato
      const segAngle = (Math.PI * 2) / ring.segments;
      for (let i = 0; i < ring.segments; i++) {
        if (i % 2 === 0) continue;
        const startAngle = i * segAngle;
        const endAngle = startAngle + segAngle * 0.6;
        ctx.globalAlpha = ring.alpha;
        ctx.beginPath();
        ctx.arc(0, 0, ring.r, startAngle, endAngle);
        ctx.stroke();
      }
    } else {
      // Anello continuo con segmenti
      const segAngle = (Math.PI * 2) / ring.segments;
      for (let i = 0; i < ring.segments; i++) {
        // Alterna spessore per effetto "tick marks"
        const isHighlight = i % 4 === 0;
        ctx.globalAlpha = isHighlight ? ring.alpha : ring.alpha * 0.5;
        ctx.lineWidth = isHighlight ? ring.thickness * 1.5 : ring.thickness;

        const startAngle = i * segAngle;
        const endAngle = startAngle + segAngle * 0.85;
        ctx.beginPath();
        ctx.arc(0, 0, ring.r, startAngle, endAngle);
        ctx.stroke();
      }
    }

    ctx.restore();
  }

  // === DRAW CORE (nucleo energetico) ===
  function drawCore(skin) {
    ctx.save();
    ctx.translate(cx, cy);

    // Outer glow halo
    const haloGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, 50);
    haloGrad.addColorStop(0, skin.glow);
    haloGrad.addColorStop(0.5, skin.glow.replace("0.6", "0.2"));
    haloGrad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = haloGrad;
    ctx.beginPath();
    ctx.arc(0, 0, 50, 0, Math.PI * 2);
    ctx.fill();

    // Nucleo esterno pulsante
    const pulse = 1 + Math.sin(state.corePulse) * 0.15;
    const outerR = 32 * pulse;

    ctx.shadowColor = skin.glow;
    ctx.shadowBlur = 30;
    ctx.fillStyle = skin.bg;
    ctx.strokeStyle = skin.primary;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(0, 0, outerR, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // Secondo anello interno
    const innerR = 22 * pulse;
    ctx.strokeStyle = skin.secondary;
    ctx.lineWidth = 1.5;
    ctx.shadowBlur = 20;
    ctx.beginPath();
    ctx.arc(0, 0, innerR, 0, Math.PI * 2);
    ctx.stroke();

    // Nucleo centrale luminoso
    const coreGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, 18);
    coreGrad.addColorStop(0, skin.coreInner);
    coreGrad.addColorStop(0.4, skin.coreOuter);
    coreGrad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = coreGrad;
    ctx.shadowBlur = 40;
    ctx.beginPath();
    ctx.arc(0, 0, 18, 0, Math.PI * 2);
    ctx.fill();

    // Punto centrale brillante
    ctx.fillStyle = "#ffffff";
    ctx.shadowBlur = 20;
    ctx.beginPath();
    ctx.arc(0, 0, 4 * pulse, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }

  // === DRAW WAVEFORM (audio reattivo) ===
  function drawWaveform(skin) {
    ctx.save();
    ctx.translate(cx, cy);

    const baseR = 200;
    const bars = state.waveform.length;

    for (let i = 0; i < bars; i++) {
      const angle = (i / bars) * Math.PI * 2 - Math.PI / 2;
      const amplitude = state.waveform[i];
      const barLength = 5 + amplitude * 30;

      const x1 = Math.cos(angle) * baseR;
      const y1 = Math.sin(angle) * baseR;
      const x2 = Math.cos(angle) * (baseR + barLength);
      const y2 = Math.sin(angle) * (baseR + barLength);

      const alpha = 0.3 + amplitude * 0.7;
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = i % 2 === 0 ? skin.primary : skin.secondary;
      ctx.shadowColor = skin.glow;
      ctx.shadowBlur = 8;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    }

    ctx.restore();
  }

  // === DRAW SCANNING LINE ===
  function drawScanner(skin) {
    ctx.save();
    ctx.translate(cx, cy);

    state.scanAngle += 0.015;
    if (state.scanAngle > Math.PI * 2) state.scanAngle -= Math.PI * 2;

    const grad = ctx.createLinearGradient(0, 0, Math.cos(state.scanAngle) * 180, Math.sin(state.scanAngle) * 180);
    grad.addColorStop(0, "rgba(0,0,0,0)");
    grad.addColorStop(1, skin.glow);

    ctx.strokeStyle = grad;
    ctx.lineWidth = 2;
    ctx.shadowColor = skin.glow;
    ctx.shadowBlur = 15;

    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.cos(state.scanAngle) * 180, Math.sin(state.scanAngle) * 180);
    ctx.stroke();

    // Punto di scansione
    ctx.fillStyle = skin.accent;
    ctx.beginPath();
    ctx.arc(Math.cos(state.scanAngle) * 180, Math.sin(state.scanAngle) * 180, 3, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }

  // === DRAW PARTICLES ===
  function drawParticles(skin) {
    ctx.save();
    for (const p of state.particles) {
      p.angle += p.speed;
      p.pulse += 0.05;

      const x = cx + Math.cos(p.angle) * p.radius;
      const y = cy + Math.sin(p.angle) * p.radius;

      const alphaPulse = p.alpha * (0.6 + Math.sin(p.pulse) * 0.4);
      ctx.globalAlpha = alphaPulse;
      ctx.fillStyle = skin.primary;
      ctx.shadowColor = skin.glow;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.arc(x, y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // === DRAW DATA STREAM (numeri esadecimali ai lati) ===
  function drawDataStream(skin) {
    ctx.save();
    ctx.font = "10px 'SF Mono', monospace";
    ctx.fillStyle = skin.primary;
    ctx.globalAlpha = 0.5;

    for (const s of state.dataStream) {
      s.y += s.speed;
      if (s.y > SIZE + 20) {
        s.y = -20;
        s.text = Math.random().toString(16).substring(2, 8).toUpperCase();
      }
      const x = s.side === "left" ? 15 : SIZE - 55;
      ctx.fillText(s.text, x, s.y);
    }

    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // === DRAW HUD CORNERS (angoli con dati) ===
  function drawHUDCorners(skin) {
    ctx.save();
    ctx.strokeStyle = skin.primary;
    ctx.shadowColor = skin.glow;
    ctx.shadowBlur = 8;
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = 0.6;

    const padding = 15;
    const len = 30;

    // Top-left
    ctx.beginPath();
    ctx.moveTo(padding, padding + len);
    ctx.lineTo(padding, padding);
    ctx.lineTo(padding + len, padding);
    ctx.stroke();

    // Top-right
    ctx.beginPath();
    ctx.moveTo(SIZE - padding - len, padding);
    ctx.lineTo(SIZE - padding, padding);
    ctx.lineTo(SIZE - padding, padding + len);
    ctx.stroke();

    // Bottom-left
    ctx.beginPath();
    ctx.moveTo(padding, SIZE - padding - len);
    ctx.lineTo(padding, SIZE - padding);
    ctx.lineTo(padding + len, SIZE - padding);
    ctx.stroke();

    // Bottom-right
    ctx.beginPath();
    ctx.moveTo(SIZE - padding - len, SIZE - padding);
    ctx.lineTo(SIZE - padding, SIZE - padding);
    ctx.lineTo(SIZE - padding, SIZE - padding - len);
    ctx.stroke();

    // Status text in basso
    ctx.font = "9px 'SF Mono', monospace";
    ctx.fillStyle = skin.primary;
    ctx.globalAlpha = 0.8;
    ctx.textAlign = "left";
    ctx.fillText("SYSTEM ONLINE", padding + 10, SIZE - padding - 10);
    ctx.textAlign = "right";

    const uptime = Math.floor((Date.now() - state.bootedAt) / 1000);
    const uptimeStr = String(Math.floor(uptime / 60)).padStart(2, "0") + ":" + String(uptime % 60).padStart(2, "0");
    ctx.fillText("UPTIME " + uptimeStr, SIZE - padding - 10, SIZE - padding - 10);

    // Status al top
    ctx.textAlign = "center";
    const statusText = {
      idle: "● STANDBY",
      thinking: "◉ ANALYZING",
      speaking: "◉ TRANSMITTING",
      listening: "◉ LISTENING",
      happy: "● READY",
      error: "◉ ERROR",
    }[state.mood] || "● STANDBY";
    ctx.fillText(statusText, SIZE / 2, padding + 14);

    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // === UPDATE WAVEFORM ===
  function updateWaveform() {
    // Se parla, genera waveform reattiva
    if (state.mood === "speaking") {
      for (let i = 0; i < state.waveform.length; i++) {
        if (Math.random() < 0.3) {
          state.waveformTargets[i] = 0.3 + Math.random() * 0.7;
        }
      }
    } else if (state.mood === "thinking") {
      // Waveform circolare che si muove
      const t = state.time * 0.1;
      for (let i = 0; i < state.waveform.length; i++) {
        state.waveformTargets[i] = (Math.sin(i * 0.3 + t) + 1) / 2 * 0.4 + 0.1;
      }
    } else if (state.mood === "listening") {
      for (let i = 0; i < state.waveform.length; i++) {
        state.waveformTargets[i] = 0.1 + Math.abs(Math.sin(i * 0.5 + state.time * 0.2)) * 0.5;
      }
    } else {
      // Idle: calmo
      for (let i = 0; i < state.waveform.length; i++) {
        state.waveformTargets[i] = 0.05 + Math.abs(Math.sin(i * 0.2 + state.time * 0.05)) * 0.15;
      }
    }

    // Smoothing
    for (let i = 0; i < state.waveform.length; i++) {
      state.waveform[i] += (state.waveformTargets[i] - state.waveform[i]) * 0.15;
    }
  }

  // === MAIN LOOP ===
  function draw() {
    state.time++;
    state.corePulse += state.mood === "thinking" ? 0.15 : 0.05;

    ctx.clearRect(0, 0, SIZE, SIZE);

    const skin = SKINS[state.skin] || SKINS.ai;

    // Aggiorna rings
    for (const ring of state.rings) {
      ring.angle += ring.speed * (state.mood === "thinking" ? 2 : 1);
    }

    updateWaveform();

    // Draw order
    drawDataStream(skin);
    drawParticles(skin);
    drawRing(state.rings[0], skin);
    drawRing(state.rings[1], skin);
    drawRing(state.rings[2], skin);
    drawWaveform(skin);
    drawRing(state.rings[3], skin);
    drawScanner(skin);
    drawRing(state.rings[4], skin);
    drawRing(state.rings[5], skin);
    drawCore(skin);
    drawHUDCorners(skin);

    requestAnimationFrame(draw);
  }

  // === PUBLIC API ===
  window.Face = {
    setSkin(id) {
      if (SKINS[id]) {
        state.skin = id;
        return true;
      }
      return false;
    },
    setMood(mood) {
      state.mood = mood;
    },
    listSkins() {
      return Object.keys(SKINS);
    },
    getSkinName() {
      return SKINS[state.skin]?.name || "AI";
    },
  };

  initRings();
  initParticles();
  initDataStream();
  draw();
})();
