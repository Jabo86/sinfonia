(function () {
  var $ = function (id) { return document.getElementById(id); };
  var pollTimer = null;

  function openModal() {
    var m = $('orchestrator-modal'); if (m) m.classList.add('open');
    poll(); if (!pollTimer) pollTimer = setInterval(poll, 2000);
  }
  function closeModal() { var m = $('orchestrator-modal'); if (m) m.classList.remove('open'); }
  
  async function startJob() {
    var body = {
      project_dir: $('orch-project-dir').value.trim(),
      model: $('orch-model').value.trim(),
      requirements: $('orch-requirements').value.trim(),
      language: $('orch-language').value,
      clean: $('orch-clean').checked,
    };
    if (!body.project_dir || !body.requirements) { alert('Compila cartella e requirements'); return; }
    $('orch-start').disabled = true;
    try {
      var r = await fetch('/v1/orchestrator/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      });
      var j = await r.json();
      if (!r.ok || !j.ok) { 
          var msg = j.detail ? (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)) : (j.error || 'Errore HTTP ' + r.status);
          alert('Errore: ' + msg); 
          $('orch-start').disabled = false; 
          return; 
      }
      $('orch-stop').disabled = false;
      if (!pollTimer) pollTimer = setInterval(poll, 2000);
      poll();
    } catch (e) {
      alert('Errore di rete: ' + e.message);
      $('orch-start').disabled = false;
    }
  }
  
  async function stopJob() {
    try { await fetch('/v1/orchestrator/stop', { method: 'POST' }); $('orch-stop').disabled = true; }
    catch (e) { alert('Errore: ' + e.message); }
  }
  
  async function poll() {
    try {
      var r = await fetch('/v1/orchestrator/status');
      var s = await r.json();
      $('orch-status-lang').textContent = s.language || '—';
      $('orch-status-model').textContent = s.model || '—';
      $('orch-status-started').textContent = s.started_at || '—';
      $('orch-status-finished').textContent = s.finished_at || '—';
      $('orch-status-verdict').textContent = s.verdict || '—';
      var badge = $('orch-phase');
      badge.textContent = s.phase || 'idle';
      badge.className = 'badge ' + (s.running ? 'running' : s.phase === 'done' ? 'done' : s.phase === 'error' ? 'error' : 'idle');
      var logEl = $('orch-log');
      logEl.textContent = (s.log || []).join('\n') || 'In attesa...';
      logEl.scrollTop = logEl.scrollHeight;
      renderFiles(s.files || []);
      if (!s.running && pollTimer) {
        clearInterval(pollTimer); pollTimer = null;
        $('orch-start').disabled = false; $('orch-stop').disabled = true;
      }
    } catch (e) {}
  }
  
  function renderFiles(files) {
    var el = $('orch-file-list'); if (!el) return;
    if (!files.length) { el.innerHTML = '<em style="color:#6b6b80;">Nessun file ancora.</em>'; return; }
    el.innerHTML = '';
    files.forEach(function (f) {
      var row = document.createElement('div');
      row.className = 'orch-file-row';
      row.innerHTML = '<span class="path">' + f.path + '</span><span class="size">' + f.size + ' B</span>';
      row.addEventListener('click', function () { showFile(f.path); });
      el.appendChild(row);
    });
  }
  
  async function showFile(path) {
    try {
      var r = await fetch('/v1/orchestrator/file?path=' + encodeURIComponent(path));
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var j = await r.json();
      $('orch-preview-title').textContent = j.path;
      $('orch-preview-content').textContent = j.content;
      $('orch-preview').style.display = 'block';
    } catch (e) { alert('Errore lettura file: ' + e.message); }
  }

  function openImageModal() { var m = $('image-modal'); if (m) m.classList.add('open'); }
  function closeImageModal() { var m = $('image-modal'); if (m) m.classList.remove('open'); }
  
  async function generateImage() {
    var prompt = $('image-prompt').value.trim(); var model = $('image-model').value.trim();
    if (!prompt) { alert('Scrivi un prompt'); return; }
    $('image-generate').disabled = true; $('image-result').style.display = 'none';
    try {
      var body = { prompt: prompt }; if (model) body.model = model;
      var r = await fetch('/v1/images/generations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      var j = await r.json();
      if (!r.ok || j.detail) { alert('Errore: ' + (j.detail ? JSON.stringify(j.detail) : 'HTTP ' + r.status)); return; }
      $('image-result-title').textContent = (j.provider || '?') + ' · ' + (j.model || '?');
      $('image-result-img').src = j.url; $('image-result-link').href = j.url;
      $('image-result').style.display = 'block';
    } catch (e) { alert('Errore rete: ' + e.message); }
    finally { $('image-generate').disabled = false; }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var b = $('orchestrator-btn'); if (b) b.addEventListener('click', openModal);
    var c = $('orch-close'); if (c) c.addEventListener('click', closeModal);
    var s = $('orch-start'); if (s) s.addEventListener('click', startJob);
    var st = $('orch-stop'); if (st) st.addEventListener('click', stopJob);
    var m = $('orchestrator-modal'); if (m) m.addEventListener('click', function (e) { if (e.target === m) closeModal(); });
    var ib = $('image-btn'); if (ib) ib.addEventListener('click', openImageModal);
    var ic = $('image-close'); if (ic) ic.addEventListener('click', closeImageModal);
    var ig = $('image-generate'); if (ig) ig.addEventListener('click', generateImage);
    var im = $('image-modal'); if (im) im.addEventListener('click', function (e) { if (e.target === im) closeImageModal(); });
  });
})();
