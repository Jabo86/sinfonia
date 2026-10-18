(function() {
  // --- 1. SFERA 3D ---
  const container = document.createElement('div');
  container.id = 'jarvis-canvas-container';
  document.body.prepend(container);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  container.appendChild(renderer.domElement);
  camera.position.z = 7;

  const particleCount = 6000;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(particleCount * 3);
  const velocities = new Float32Array(particleCount * 3);

  for (let i = 0; i < particleCount; i++) {
    const phi = Math.acos(2 * Math.random() - 1);
    const theta = Math.random() * Math.PI * 2;
    const r = 1.6 + Math.random() * 0.1;
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
    velocities[i * 3] = (Math.random() - 0.5) * 0.005;
    velocities[i * 3 + 1] = (Math.random() - 0.5) * 0.005;
    velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.005;
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

  function createParticleTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 32; canvas.height = 32;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.4, 'rgba(255,255,255,0.8)');
    gradient.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 32, 32);
    return new THREE.CanvasTexture(canvas);
  }

  const material = new THREE.PointsMaterial({
    size: 0.05, map: createParticleTexture(), color: 0x00d2ff,
    transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false
  });
  const particles = new THREE.Points(geometry, material);
  scene.add(particles);

  const coreGeo = new THREE.SphereGeometry(0.5, 32, 32);
  const coreMat = new THREE.MeshBasicMaterial({ color: 0x00d2ff, transparent: true, opacity: 0.1, blending: THREE.AdditiveBlending });
  const coreMesh = new THREE.Mesh(coreGeo, coreMat);
  scene.add(coreMesh);

  // --- 2. STATO ED EMOZIONI ---
  window.JarvisState = { isSpeaking: false, isThinking: false, isListening: false };
  const COLORS = { neutral: 0x00d2ff, listening: 0xff0055, thinking: 0xffaa00, speaking: 0x00ff88 };

  window.setJarvisEmotion = function(state) {
    window.JarvisState.isSpeaking = state === 'speaking';
    window.JarvisState.isThinking = state === 'thinking';
    window.JarvisState.isListening = state === 'listening';
    
    let hex = COLORS.neutral;
    if (state === 'speaking') hex = COLORS.speaking;
    else if (state === 'thinking') hex = COLORS.thinking;
    else if (state === 'listening') hex = COLORS.listening;
    
    material.color.setHex(hex);
    coreMat.color.setHex(hex);
  };

  const clock = new THREE.Clock();
  function animate() {
    requestAnimationFrame(animate);
    const t = clock.getElapsedTime();
    const pos = geometry.attributes.position.array;

    for (let i = 0; i < particleCount; i++) {
      pos[i * 3] += velocities[i * 3];
      pos[i * 3 + 1] += velocities[i * 3 + 1];
      pos[i * 3 + 2] += velocities[i * 3 + 2];
      const dist = Math.sqrt(pos[i*3]**2 + pos[i*3+1]**2 + pos[i*3+2]**2);
      if (dist > 1.8 || dist < 1.4) {
        velocities[i * 3] *= -0.5; velocities[i * 3 + 1] *= -0.5; velocities[i * 3 + 2] *= -0.5;
      }
    }
    geometry.attributes.position.needsUpdate = true;

    particles.rotation.y += 0.003;
    particles.rotation.x = Math.sin(t * 0.3) * 0.1;

    if (window.JarvisState.isSpeaking) {
      const pulse = 1 + Math.sin(t * 15) * 0.05;
      particles.scale.set(pulse, pulse, pulse);
      coreMesh.scale.set(pulse * 1.2, pulse * 1.2, pulse * 1.2);
      coreMat.opacity = 0.4 + Math.sin(t * 15) * 0.1;
    } else if (window.JarvisState.isThinking) {
      const pulse = 1 + Math.sin(t * 5) * 0.03;
      particles.scale.set(pulse, pulse, pulse);
      coreMat.opacity = 0.3;
    } else if (window.JarvisState.isListening) {
      const pulse = 1 + Math.sin(t * 8) * 0.02;
      particles.scale.set(pulse, pulse, pulse);
      coreMat.opacity = 0.2;
    } else {
      const breath = 1 + Math.sin(t * 2) * 0.02;
      particles.scale.set(breath, breath, breath);
      coreMat.opacity = 0.1 + Math.sin(t * 2) * 0.05;
    }
    renderer.render(scene, camera);
  }
  animate();

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  // --- 3. GESTIONE VOCE (HANDS-FREE LOOP) ---
  const synth = window.speechSynthesis;
  let voices = [];
  function loadVoices() { voices = synth.getVoices(); if (voices.length === 0) setTimeout(loadVoices, 250); }
  loadVoices(); synth.onvoiceschanged = loadVoices;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let keepListening = false;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'it-IT';
    recognition.continuous = false; // Importante: false, ma lo facciamo ripartire noi da codice
    recognition.interimResults = false;

    recognition.onstart = () => window.setJarvisEmotion('listening');

    recognition.onend = () => {
      window.setJarvisEmotion(window.JarvisState.isSpeaking || window.JarvisState.isThinking ? 'neutral' : 'neutral');
      // SE IL LOOP È ATTIVO, RICOMINCIA AD ASCOLTARE DOPO AVER PARLATO
      if (keepListening && !window.JarvisState.isSpeaking && !window.JarvisState.isThinking) {
        setTimeout(startListening, 500);
      }
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      if (!transcript.trim()) return;

      // Inserisce il testo nella barra di Sinfonia
      const inputField = document.getElementById('input');
      if (inputField) {
        inputField.value = transcript;
        inputField.dispatchEvent(new Event('input', { bubbles: true }));
        // Clicca Invia
        setTimeout(() => {
          const sendBtn = document.getElementById('send');
          if (sendBtn) sendBtn.click();
        }, 100);
      }
    };

    recognition.onerror = (event) => {
      if (event.error !== 'no-speech') {
        console.error("Errore STT:", event.error);
        window.setJarvisEmotion('neutral');
      }
    };
  }

  function startListening() {
    if (!recognition || window.JarvisState.isSpeaking) return;
    try { recognition.start(); } catch(e) { setTimeout(startListening, 500); }
  }

  function speakJarvis(text) {
    if (!text) return;
    synth.cancel();
    
    let clean = text;
    if (clean.includes('Risultato finale')) clean = clean.split('Risultato finale').pop();
    clean = clean.replace(/^[-*]\s+/gm, '').replace(/[#*`]/g, '').trim();

    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = 'it-IT';
    utterance.rate = 1.0;
    utterance.pitch = 0.9;
    const itVoice = voices.find(v => v.lang.includes('it') && (v.name.includes('Male') || v.name.includes('Luca') || v.name.includes('Diego'))) || voices.find(v => v.lang.includes('it'));
    if (itVoice) utterance.voice = itVoice;

    utterance.onend = () => {
      window.setJarvisEmotion('neutral');
      // SE IL LOOP È ATTIVO, RICOMINCIA AD ASCOLTARE DOPO AVER PARLATO
      if (keepListening) setTimeout(startListening, 500);
    };
    
    setTimeout(() => synth.speak(utterance), 100);
  }

  // --- 4. INTEGRAZIONE CON SINFONIA ---
  
  // Intercetta la risposta del server
  const originalFetch = window.fetch;
  window.fetch = async function(url, options) {
    if (typeof url === 'string' && url.includes('/v1/chat/completions') && options && options.method === 'POST') {
      window.setJarvisEmotion('thinking');
      try {
        const response = await originalFetch.apply(this, arguments);
        const clonedResponse = response.clone();
        
        clonedResponse.json().then(data => {
          const reply = data.choices?.[0]?.message?.content;
          if (reply) {
            window.setJarvisEmotion('speaking');
            speakJarvis(reply);
          } else {
            window.setJarvisEmotion('neutral');
          }
        }).catch(() => window.setJarvisEmotion('neutral'));
        return response;
      } catch (e) {
        window.setJarvisEmotion('neutral');
        throw e;
      }
    }
    return originalFetch.apply(this, arguments);
  };

  // Dirotta il bottone "Voce" originale
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
      const oldVoiceBtn = document.getElementById('voice-toggle');
      if (!oldVoiceBtn) return;

      // Clona il bottone per rimuovere i vecchi listener
      const newVoiceBtn = oldVoiceBtn.cloneNode(true);
      oldVoiceBtn.parentNode.replaceChild(newVoiceBtn, oldVoiceBtn);

      newVoiceBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (keepListening) {
          // Ferma tutto
          keepListening = false;
          newVoiceBtn.classList.remove('active');
          if (recognition) recognition.stop();
          synth.cancel();
          window.setJarvisEmotion('neutral');
        } else {
          // Avvia modalità Hands-Free
          keepListening = true;
          newVoiceBtn.classList.add('active');
          synth.cancel();
          speakJarvis("Sistemi online. Sono in ascolto.");
        }
      });
    }, 1000);
  });
})();
