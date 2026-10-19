(function() {
  // --- SFERA 3D ---
  const container = document.createElement('div');
  container.id = 'jarvis-canvas-container';
  container.style.cssText = 'position:fixed; inset:0; z-index:1; pointer-events:none; display:flex; justify-content:center; align-items:center; opacity:0.6;';
  document.body.prepend(container);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  container.appendChild(renderer.domElement);
  camera.position.z = 7;

  const particleCount = 5000;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i++) {
    const phi = Math.acos(2 * Math.random() - 1);
    const theta = Math.random() * Math.PI * 2;
    const r = 1.6 + Math.random() * 0.1;
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  function createParticleTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 32; canvas.height = 32;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 32, 32);
    return new THREE.CanvasTexture(canvas);
  }

  const material = new THREE.PointsMaterial({ size: 0.05, map: createParticleTexture(), color: 0x00d2ff, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending });
  const particles = new THREE.Points(geometry, material);
  scene.add(particles);

  let isSpeaking = false;
  function animate() {
    requestAnimationFrame(animate);
    particles.rotation.y += 0.003;
    if (isSpeaking) { const p = 1 + Math.sin(Date.now() * 0.01) * 0.05; particles.scale.set(p, p, p); } 
    else { particles.scale.lerp(new THREE.Vector3(1, 1, 1), 0.1); }
    renderer.render(scene, camera);
  }
  animate();

  // --- VOCE (TTS) ---
  const synth = window.speechSynthesis;
  let voices = [];
  synth.onvoiceschanged = () => { voices = synth.getVoices(); };
  
  // FUNZIONE DI PULIZIA PER NON FAR DIRE "PUNTO"
  function cleanForSpeech(text) {
    let clean = text;
    // Rimuove elenchi puntati e markdown
    clean = clean.replace(/^[-*•]\s+/gm, '');
    clean = clean.replace(/[*#_`~]/g, '');
    // Sostituisce gli a capo con delle virgole per far scorrere la voce
    clean = clean.replace(/\n+/g, ', ');
    // Rimuove i doppi spazi
    clean = clean.replace(/\s+/g, ' ');
    // Rimuove i punti isolati
    clean = clean.replace(/\.\s*\./g, '.');
    return clean.trim();
  }

  function speak(text) {
    if (!text) return;
    synth.cancel();
    const clean = cleanForSpeech(text);
    
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = 'it-IT';
    utterance.pitch = 0.9;
    utterance.rate = 1.05; 
    
    const itVoice = voices.find(v => v.lang.includes('it'));
    if (itVoice) utterance.voice = itVoice;
    
    utterance.onstart = () => { isSpeaking = true; };
    utterance.onend = () => { 
      isSpeaking = false; 
      if (isMicOn && recognition) {
        try { recognition.start(); } catch(e) {}
      }
    };
    synth.speak(utterance);
  }

  // --- ASCOLTO (STT) ---
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isMicOn = false;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'it-IT';
    recognition.continuous = true;
    recognition.interimResults = false;

    recognition.onstart = () => {
      isMicOn = true;
      const btn = document.getElementById('voice-toggle');
      if (btn) btn.classList.add('active');
    };

    recognition.onend = () => {
      if (isMicOn) {
        setTimeout(() => { try { recognition.start(); } catch(e) {} }, 1000);
      } else {
        const btn = document.getElementById('voice-toggle');
        if (btn) btn.classList.remove('active');
      }
    };

    recognition.onresult = (event) => {
      const text = event.results[event.results.length - 1][0].transcript.toLowerCase().trim();
      if (!text) return;
      
      const input = document.getElementById('input');
      if (input) { 
        input.value = text; 
        input.dispatchEvent(new Event('input', { bubbles: true })); 
        setTimeout(() => document.getElementById('send')?.click(), 100); 
      }
    };
  }

  // --- GESTIONE PULSANTE ---
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
      const oldBtn = document.getElementById('voice-toggle');
      if (!oldBtn) return;
      
      const newBtn = oldBtn.cloneNode(true);
      oldBtn.parentNode.replaceChild(newBtn, oldBtn);
      
      newBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (isMicOn) {
          isMicOn = false;
          if (recognition) recognition.stop();
          synth.cancel();
          newBtn.classList.remove('active');
        } else {
          isMicOn = true;
          synth.cancel();
          try { recognition.start(); } catch(e) { alert("Errore microfono: " + e.message); }
          newBtn.classList.add('active');
          speak("Sistemi online. Sono ULTRON.");
        }
      });
    }, 1000);
  });

  // --- LEGGI RISPOSTE DELLA CHAT ---
  const msgContainer = document.getElementById('messages');
  if (msgContainer) {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((m) => {
        m.addedNodes.forEach((node) => {
          if (node.classList && node.classList.contains('msg') && node.classList.contains('assistant')) {
            setTimeout(() => {
              const txt = node.innerText || node.textContent;
              if (txt && txt.trim().length > 0) speak(txt);
            }, 500);
          }
        });
      });
    });
    observer.observe(msgContainer, { childList: true, subtree: true });
  }
})();
