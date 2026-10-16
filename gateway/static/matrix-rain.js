(function() {
  const canvas = document.getElementById("matrix-rain");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let width, height, columns, drops;
  const fontSize = 16;
  const chars = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
    columns = Math.floor(width / fontSize);
    drops = new Array(columns).fill(1);
  }
  function draw() {
    ctx.fillStyle = "rgba(0, 0, 0, 0.06)";
    ctx.fillRect(0, 0, width, height);
    ctx.font = fontSize + "px 'Courier New', monospace";
    for (let i = 0; i < drops.length; i++) {
      const char = chars[Math.floor(Math.random() * chars.length)];
      const x = i * fontSize;
      const y = drops[i] * fontSize;
      const rand = Math.random();
      if (rand > 0.975) { ctx.fillStyle = "#c8ffe0"; ctx.shadowColor = "#00ff88"; ctx.shadowBlur = 12; }
      else if (rand > 0.9) { ctx.fillStyle = "#00ff88"; ctx.shadowColor = "#00ff88"; ctx.shadowBlur = 8; }
      else { ctx.fillStyle = "#0a8a4a"; ctx.shadowBlur = 0; }
      ctx.fillText(char, x, y);
      if (y > height && Math.random() > 0.975) drops[i] = 0;
      drops[i]++;
    }
    ctx.shadowBlur = 0;
  }
  resize();
  window.addEventListener("resize", resize);
  setInterval(draw, 45);
})();
