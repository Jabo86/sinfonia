(function() {
  const canvas = document.getElementById("face-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const SIZE = 320;
  canvas.width = SIZE * 2;
  canvas.height = SIZE * 2;
  canvas.style.width = SIZE + "px";
  canvas.style.height = SIZE + "px";
  ctx.scale(2, 2);
  const cx = SIZE / 2;
  const cy = SIZE / 2;
  const state = { skin: "ai", mood: "idle", blinkTimer: 0, blinkDuration: 0, mouthOpen: 0, mouthTarget: 0, lookX: 0, lookY: 0, time: 0, particles: [] };
  const SKINS = {
    ai: { name: "AI", headColor: "#0a3d2c", headStroke: "#00ff88", headGlow: "#00ff88", eyeColor: "#00ff88", eyeGlow: "#00ffaa", pupilColor: "#000", mouthColor: "#00ff88", accent: "#00ff88", shape: "circle" },
    dragon: { name: "Drago", headColor: "#3d1005", headStroke: "#ff4400", headGlow: "#ff4400", eyeColor: "#ffcc00", eyeGlow: "#ff6600", pupilColor: "#000", mouthColor: "#ff4400", accent: "#ffcc00", shape: "dragon" },
    cat: { name: "Gatto", headColor: "#2a1a0a", headStroke: "#ffaa44", headGlow: "#ffaa44", eyeColor: "#44ff88", eyeGlow: "#88ffaa", pupilColor: "#000", mouthColor: "#ffaa44", accent: "#ffaa44", shape: "cat" },
    alien: { name: "Alieno", headColor: "#1a0a2a", headStroke: "#cc44ff", headGlow: "#cc44ff", eyeColor: "#44ffcc", eyeGlow: "#44ffcc", pupilColor: "#000", mouthColor: "#cc44ff", accent: "#cc44ff", shape: "alien" },
    human: { name: "Umano", headColor: "#1a1a1a", headStroke: "#88ccff", headGlow: "#88ccff", eyeColor: "#ffffff", eyeGlow: "#88ccff", pupilColor: "#0066cc", mouthColor: "#88ccff", accent: "#88ccff", shape: "human" },
    ghost: { name: "Fantasma", headColor: "rgba(200, 200, 255, 0.15)", headStroke: "#aaccff", headGlow: "#aaccff", eyeColor: "#ffffff", eyeGlow: "#aaccff", pupilColor: "#000", mouthColor: "#aaccff", accent: "#aaccff", shape: "ghost" },
    fire: { name: "Fuoco", headColor: "#2a0800", headStroke: "#ff6600", headGlow: "#ffcc00", eyeColor: "#ffff00", eyeGlow: "#ff6600", pupilColor: "#000", mouthColor: "#ff6600", accent: "#ffcc00", shape: "fire" }
  };
  function drawHead(skin) {
    ctx.save();
    ctx.shadowColor = skin.headGlow; ctx.shadowBlur = 25;
    ctx.strokeStyle = skin.headStroke; ctx.lineWidth = 2.5; ctx.fillStyle = skin.headColor;
    if (skin.shape === "dragon") {
      ctx.beginPath();
      ctx.moveTo(cx-60, cy-30); ctx.lineTo(cx-80, cy-80); ctx.lineTo(cx-55, cy-55);
      ctx.lineTo(cx-40, cy-90); ctx.lineTo(cx, cy-65); ctx.lineTo(cx+40, cy-90);
      ctx.lineTo(cx+55, cy-55); ctx.lineTo(cx+80, cy-80); ctx.lineTo(cx+60, cy-30);
      ctx.quadraticCurveTo(cx+65, cy+60, cx, cy+75);
      ctx.quadraticCurveTo(cx-65, cy+60, cx-60, cy-30);
      ctx.closePath(); ctx.fill(); ctx.stroke();
    } else if (skin.shape === "cat") {
      ctx.beginPath();
      ctx.moveTo(cx-70, cy-20); ctx.lineTo(cx-75, cy-95); ctx.lineTo(cx-30, cy-70);
      ctx.lineTo(cx, cy-85); ctx.lineTo(cx+30, cy-70); ctx.lineTo(cx+75, cy-95);
      ctx.lineTo(cx+70, cy-20);
      ctx.quadraticCurveTo(cx+75, cy+65, cx, cy+80);
      ctx.quadraticCurveTo(cx-75, cy+65, cx-70, cy-20);
      ctx.closePath(); ctx.fill(); ctx.stroke();
    } else if (skin.shape === "alien") {
      ctx.beginPath(); ctx.ellipse(cx, cy+5, 65, 80, 0, 0, Math.PI*2); ctx.fill(); ctx.stroke();
    } else if (skin.shape === "ghost") {
      ctx.beginPath();
      ctx.arc(cx, cy-10, 70, Math.PI, 0);
      ctx.lineTo(cx+70, cy+40); ctx.lineTo(cx+55, cy+30); ctx.lineTo(cx+40, cy+55);
      ctx.lineTo(cx+20, cy+35); ctx.lineTo(cx, cy+60); ctx.lineTo(cx-20, cy+35);
      ctx.lineTo(cx-40, cy+55); ctx.lineTo(cx-55, cy+30); ctx.lineTo(cx-70, cy+40);
      ctx.closePath(); ctx.fill(); ctx.stroke();
    } else if (skin.shape === "fire") {
      ctx.beginPath();
      ctx.moveTo(cx, cy-95);
      for (let i = 0; i <= 20; i++) {
        const angle = (i/20)*Math.PI*2 - Math.PI/2;
        const base = 65;
        const wobble = Math.sin(angle*5 + state.time*0.05) * 8;
        const r = base + wobble;
        ctx.lineTo(cx + Math.cos(angle)*r, cy + Math.sin(angle)*r);
      }
      ctx.closePath(); ctx.fill(); ctx.stroke();
    } else if (skin.shape === "human") {
      ctx.beginPath(); ctx.ellipse(cx, cy, 62, 78, 0, 0, Math.PI*2); ctx.fill(); ctx.stroke();
      ctx.beginPath();
      ctx.ellipse(cx-62, cy+5, 8, 15, 0, 0, Math.PI*2);
      ctx.ellipse(cx+62, cy+5, 8, 15, 0, 0, Math.PI*2);
      ctx.fill(); ctx.stroke();
    } else {
      ctx.beginPath(); ctx.arc(cx, cy, 80, 0, Math.PI*2); ctx.fill(); ctx.stroke();
    }
    ctx.restore();
  }
  function drawAntenna(skin) {
    if (skin.shape === "ai") {
      ctx.save();
      ctx.strokeStyle = skin.headStroke; ctx.lineWidth = 2;
      ctx.shadowColor = skin.headGlow; ctx.shadowBlur = 15;
      ctx.beginPath(); ctx.moveTo(cx, cy-80); ctx.lineTo(cx, cy-105); ctx.stroke();
      ctx.beginPath(); ctx.arc(cx, cy-112, 8, 0, Math.PI*2);
      ctx.fillStyle = skin.accent; ctx.fill();
      ctx.restore();
    }
  }
  function drawEyes(skin) {
    const isBlinking = state.blinkDuration > 0;
    let eyeH = 20;
    if (isBlinking) eyeH = 2;
    else if (state.mood === "surprised") eyeH = 30;
    const eyeY = cy - 10;
    const eyeSpacing = skin.shape === "alien" ? 45 : 30;
    const lookOffsetX = state.lookX * 4;
    const lookOffsetY = state.lookY * 3;
    ctx.save();
    ctx.shadowColor = skin.eyeGlow; ctx.shadowBlur = 20;
    ctx.beginPath(); ctx.ellipse(cx-eyeSpacing, eyeY, 16, eyeH, 0, 0, Math.PI*2);
    ctx.fillStyle = skin.eyeColor; ctx.fill();
    ctx.strokeStyle = skin.headStroke; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.beginPath(); ctx.ellipse(cx+eyeSpacing, eyeY, 16, eyeH, 0, 0, Math.PI*2);
    ctx.fill(); ctx.stroke();
    if (!isBlinking) {
      ctx.fillStyle = skin.pupilColor; ctx.shadowBlur = 0;
      ctx.beginPath(); ctx.arc(cx-eyeSpacing+lookOffsetX, eyeY+lookOffsetY, 5, 0, Math.PI*2); ctx.fill();
      ctx.beginPath(); ctx.arc(cx+eyeSpacing+lookOffsetX, eyeY+lookOffsetY, 5, 0, Math.PI*2); ctx.fill();
    }
    ctx.restore();
  }
  function drawMouth(skin) {
    const mouthY = cy + 35;
    const openAmount = state.mouthOpen;
    ctx.save();
    ctx.strokeStyle = skin.mouthColor; ctx.fillStyle = skin.mouthColor; ctx.lineWidth = 3;
    ctx.shadowColor = skin.headGlow; ctx.shadowBlur = 12;
    if (state.mood === "happy") {
      ctx.beginPath(); ctx.arc(cx, mouthY-5, 22, 0.15*Math.PI, 0.85*Math.PI); ctx.stroke();
    } else if (state.mood === "sad") {
      ctx.beginPath(); ctx.arc(cx, mouthY+18, 22, 1.15*Math.PI, 1.85*Math.PI); ctx.stroke();
    } else if (state.mood === "thinking") {
      ctx.beginPath(); ctx.moveTo(cx-15, mouthY);
      for (let i = 0; i <= 30; i++) {
        const x = cx-15+i; const y = mouthY + Math.sin(i*0.5 + state.time*0.2)*2;
        ctx.lineTo(x, y);
      }
      ctx.stroke();
    } else if (openAmount > 0.1) {
      ctx.beginPath(); ctx.ellipse(cx, mouthY, 20, 5+openAmount*14, 0, 0, Math.PI*2);
      ctx.fillStyle = skin.headColor; ctx.fill(); ctx.stroke();
    } else {
      ctx.beginPath(); ctx.moveTo(cx-18, mouthY); ctx.lineTo(cx+18, mouthY); ctx.stroke();
    }
    ctx.restore();
  }
  function drawParticles(skin) {
    if (state.particles.length === 0) {
      for (let i = 0; i < 20; i++) {
        state.particles.push({ angle: Math.random()*Math.PI*2, radius: 110+Math.random()*30, speed: 0.002+Math.random()*0.005, size: 1+Math.random()*2, alpha: 0.3+Math.random()*0.5 });
      }
    }
    ctx.save();
    ctx.shadowColor = skin.accent; ctx.shadowBlur = 10;
    for (const p of state.particles) {
      p.angle += p.speed;
      const x = cx + Math.cos(p.angle)*p.radius;
      const y = cy + Math.sin(p.angle)*p.radius*0.6;
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = skin.accent;
      ctx.beginPath(); ctx.arc(x, y, p.size, 0, Math.PI*2); ctx.fill();
    }
    ctx.globalAlpha = 1; ctx.restore();
  }
  function draw() {
    state.time++;
    ctx.clearRect(0, 0, SIZE, SIZE);
    const skin = SKINS[state.skin] || SKINS.ai;
    if (state.blinkTimer <= 0 && Math.random() < 0.008) { state.blinkTimer = 8; state.blinkDuration = 8; }
    if (state.blinkTimer > 0) state.blinkTimer--;
    if (state.blinkDuration > 0) state.blinkDuration--;
    if (state.mood === "speaking") {
      state.mouthOpen += (Math.random() - 0.5) * 0.5;
      state.mouthOpen = Math.max(0, Math.min(1, state.mouthOpen));
    } else {
      state.mouthOpen += (state.mouthTarget - state.mouthOpen) * 0.15;
    }
    if (state.mood === "idle" && Math.random() < 0.01) {
      state.lookX = (Math.random() - 0.5) * 2;
      state.lookY = (Math.random() - 0.5) * 2;
    }
    state.lookX *= 0.98;
    state.lookY *= 0.98;
    drawParticles(skin); drawHead(skin); drawAntenna(skin); drawEyes(skin); drawMouth(skin);
    requestAnimationFrame(draw);
  }
  window.Face = {
    setSkin(id) { if (SKINS[id]) { state.skin = id; state.particles = []; return true; } return false; },
    setMood(m) { state.mood = m; if (m==="happy") state.mouthTarget = 0.3; else state.mouthTarget = 0; },
    listSkins() { return Object.keys(SKINS); },
    getSkinName() { return SKINS[state.skin]?.name || "AI"; }
  };
  draw();
})();
