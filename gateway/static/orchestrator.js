const $ = (id) => document.getElementById(id);
let pollTimer = null;

async function start() {
  const body = {
    project_dir: $('projectDir').value.trim(),
    model: $('model').value.trim(),
    requirements: $('requirements').value.trim(),
    clean: $('clean').checked,
  };
  if (!body.project_dir || !body.requirements) {
    alert('Compila cartella e requirements');
    return;
  }
  $('startBtn').disabled = true;
  const r = await fetch('/v1/orchestrator/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const j = await r.json();
  if (!j.ok) {
    alert('Errore: ' + (j.error || 'sconosciuto'));
    $('startBtn').disabled = false;
    return;
  }
  $('stopBtn').disabled = false;
  if (!pollTimer) pollTimer = setInterval(poll, 2000);
  poll();
}

async function stop() {
  await fetch('/v1/orchestrator/stop', { method: 'POST' });
  $('stopBtn').disabled = true;
}

async function poll() {
  const r = await fetch('/v1/orchestrator/status');
  const s = await r.json();
  $('statusModel').textContent = s.model || '—';
  $('statusStarted').textContent = s.started_at || '—';
  $('statusFinished').textContent = s.finished_at || '—';
  $('statusVerdict').textContent = s.verdict || '—';
  const badge = $('phaseBadge');
  badge.textContent = s.phase;
  badge.className = 'badge ' + (s.running ? 'running' : s.phase === 'done' ? 'done' : s.phase === 'error' ? 'error' : 'idle');

  const logEl = $('log');
  logEl.textContent = (s.log || []).join('\n') || 'In attesa...';
  logEl.scrollTop = logEl.scrollHeight;

  renderFiles(s.files || []);

  if (!s.running && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
    $('startBtn').disabled = false;
    $('stopBtn').disabled = true;
  }
}

function renderFiles(files) {
  const el = $('files');
  if (!files.length) {
    el.innerHTML = '<em style="color: #8b949e;">Nessun file ancora.</em>';
    return;
  }
  el.innerHTML = '';
  files.forEach(f => {
    const row = document.createElement('div');
    row.className = 'file-row';
    row.innerHTML = `<span class="file-path">${f.path}</span><span class="file-size">${f.size} B</span>`;
    row.onclick = () => showFile(f.path);
    el.appendChild(row);
  });
}

async function showFile(path) {
  const r = await fetch('/v1/orchestrator/file?path=' + encodeURIComponent(path));
  if (!r.ok) { alert('Errore lettura file'); return; }
  const j = await r.json();
  $('previewTitle').textContent = j.path;
  $('previewContent').textContent = j.content;
  $('preview').style.display = 'block';
  $('preview').scrollIntoView({ behavior: 'smooth' });
}

$('startBtn').addEventListener('click', start);
$('stopBtn').addEventListener('click', stop);
poll();
