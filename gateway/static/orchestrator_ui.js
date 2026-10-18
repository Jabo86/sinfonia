(function () {
  const $ = (id) => document.getElementById(id);
  let pollTimer = null;

  function openModal() {
    const m = $('orchestrator-modal');
    if (m) m.classList.add('open');
    poll();
    if (!pollTimer) pollTimer = setInterval(poll, 2000);
  }

  function closeModal() {
    const m = $('orchestrator-modal');
    if (m) m.classList.remove('open');
  }

  async function startJob() {
    const body = {
      project_dir: $('orch-project-dir').value.trim(),
      model: $('orch-model').value.trim(),
      requirements: $('orch-requirements').value.trim(),
      clean: $('orch-clean').checked,
    };
    if (!body.project_dir || !body.requirements) {
      alert('Compila cartella progetto e requirements.');
      return;
    }
    $('orch-start').disabled = true;
    try {
      const r = await fetch('/v1/orchestrator/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j.ok) {
        alert('Errore: ' + (j.error || 'sconosciuto'));
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
    try {
      await fetch('/v1/orchestrator/stop', { method: 'POST' });
      $('orch-stop').disabled = true;
    } catch (e) {
      alert('Errore: ' + e.message);
    }
  }

  async function poll() {
    try {
      const r = await fetch('/v1/orchestrator/status');
      const s = await r.json();

      $('orch-status-model').textContent = s.model || '—';
      $('orch-status-started').textContent = s.started_at || '—';
      $('orch-status-finished').textContent = s.finished_at || '—';
      $('orch-status-verdict').textContent = s.verdict || '—';

      const badge = $('orch-phase');
      badge.textContent = s.phase || 'idle';
      badge.className = 'badge ' + (
        s.running ? 'running' :
        s.phase === 'done' ? 'done' :
        s.phase === 'error' ? 'error' : 'idle'
      );

      const logEl = $('orch-log');
      logEl.textContent = (s.log || []).join('\n') || 'In attesa...';
      logEl.scrollTop = logEl.scrollHeight;

      renderFiles(s.files || []);

      if (!s.running && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
        $('orch-start').disabled = false;
        $('orch-stop').disabled = true;
      }
    } catch (e) {
      // rete momentaneamente giù, ignora
    }
  }

  function renderFiles(files) {
    const el = $('orch-file-list');
    if (!el) return;
    if (!files.length) {
      el.innerHTML = '<em style="color:#6b6b80;">Nessun file ancora.</em>';
      return;
    }
    el.innerHTML = '';
    files.forEach(f => {
      const row = document.createElement('div');
      row.className = 'orch-file-row';
      row.innerHTML = '<span class="path">' + f.path + '</span><span class="size">' + f.size + ' B</span>';
      row.addEventListener('click', () => showFile(f.path));
      el.appendChild(row);
    });
  }

  async function showFile(path) {
    try {
      const r = await fetch('/v1/orchestrator/file?path=' + encodeURIComponent(path));
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      $('orch-preview-title').textContent = j.path;
      $('orch-preview-content').textContent = j.content;
      $('orch-preview').style.display = 'block';
    } catch (e) {
      alert('Errore lettura file: ' + e.message);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const btn = $('orchestrator-btn');
    if (btn) btn.addEventListener('click', openModal);
    const close = $('orch-close');
    if (close) close.addEventListener('click', closeModal);
    const start = $('orch-start');
    if (start) start.addEventListener('click', startJob);
    const stop = $('orch-stop');
    if (stop) stop.addEventListener('click', stopJob);

    const modal = $('orchestrator-modal');
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
      });
    }
  });
})();
