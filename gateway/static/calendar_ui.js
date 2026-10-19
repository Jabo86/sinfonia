(function() {
  const $ = (id) => document.getElementById(id);
  let currentDate = new Date();
  let allEvents = [];
  let selectedDate = null;

  function openModal() { $('calendar-modal').classList.add('open'); loadEvents(); loadAlarms(); }
  function closeModal() { $('calendar-modal').classList.remove('open'); }

  async function loadEvents() {
    try {
      const r = await fetch('/v1/calendar/list');
      const data = await r.json();
      allEvents = data.events || [];
      renderCalendar();
      if (selectedDate) showDayDetails(selectedDate);
    } catch (e) {}
  }
  
  async function loadAlarms() {
    try {
      const r = await fetch('/v1/calendar/alarms');
      const data = await r.json();
      const el = $('cal-alarm-list'); if (!el) return;
      if (!data.alarms || data.alarms.length === 0) { el.innerHTML = '<em style="color:#6b6b80;font-size:13px;">Nessuna sveglia attiva.</em>'; return; }
      el.innerHTML = '';
      data.alarms.forEach(al => {
        const div = document.createElement('div'); div.className = 'orch-row';
        div.innerHTML = `<span>🕒 ${al.time} - ${al.label}</span><button class="orch-btn danger" style="padding:2px 8px;font-size:11px;" onclick="fetch('/v1/calendar/alarms/${al.id}',{method:'DELETE'}).then(()=>loadAlarms())">🗑️</button>`;
        el.appendChild(div);
      });
    } catch(e) {}
  }

  function renderCalendar() {
    const year = currentDate.getFullYear(), month = currentDate.getMonth();
    const monthNames = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
    $('cal-month-title').textContent = `${monthNames[month]} ${year}`;
    const grid = $('cal-grid'); grid.innerHTML = '';
    ['Lun','Mar','Mer','Gio','Ven','Sab','Dom'].forEach(d => { const el = document.createElement('div'); el.className = 'cal-day-name'; el.textContent = d; grid.appendChild(el); });
    const firstDay = new Date(year, month, 1).getDay(), daysInMonth = new Date(year, month + 1, 0).getDate();
    let startOffset = firstDay === 0 ? 6 : firstDay - 1;
    for (let i = 0; i < startOffset; i++) { const el = document.createElement('div'); el.className = 'cal-cell'; el.style.opacity = '0.3'; grid.appendChild(el); }
    const now = new Date(), todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
    for (let day = 1; day <= daysInMonth; day++) {
      const el = document.createElement('div'); el.className = 'cal-cell';
      const dateStr = `${year}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
      if (dateStr === todayStr) el.classList.add('today');
      if (dateStr === selectedDate) el.classList.add('selected');
      const dayEvents = allEvents.filter(e => e.date === dateStr);
      let evHtml = '';
      if (dayEvents.length === 1) evHtml = `<span class="cal-ev-dot"></span><span style="font-size:10px;color:#9a9ab0;">${dayEvents[0].title}</span>`;
      else if (dayEvents.length > 1) evHtml = `<span class="cal-ev-badge">${dayEvents.length} eventi</span>`;
      el.innerHTML = `<span class="cal-date-num">${day}</span>${evHtml}`;
      el.onclick = () => { selectedDate = dateStr; renderCalendar(); showDayDetails(dateStr); };
      grid.appendChild(el);
    }
  }

  function showDayDetails(dateStr) {
    const titleEl = $('cal-day-title'), listEl = $('cal-day-list');
    const [y, m, d] = dateStr.split('-'); titleEl.textContent = `Note del ${d}/${m}/${y}`;
    const dayEvents = allEvents.filter(e => e.date === dateStr);
    if (dayEvents.length === 0) { listEl.innerHTML = '<em>Nessun evento.</em>'; return; }
    listEl.innerHTML = '';
    dayEvents.forEach(ev => {
      const div = document.createElement('div'); div.className = 'orch-row';
      div.innerHTML = `<span>${ev.time ? ev.time + ' - ' : ''}${ev.title}</span><button class="orch-btn danger" style="padding:2px 8px;font-size:11px;" onclick="fetch('/v1/calendar/delete/${ev.id}',{method:'DELETE'}).then(()=>document.dispatchEvent(new Event('refresh_calendar')))">🗑️</button>`;
      listEl.appendChild(div);
    });
  }

  document.addEventListener('refresh_calendar', loadEvents);
  document.addEventListener('DOMContentLoaded', () => {
    if ($('calendar-btn')) $('calendar-btn').addEventListener('click', openModal);
    if ($('cal-close')) $('cal-close').addEventListener('click', closeModal);
    if ($('cal-prev')) $('cal-prev').addEventListener('click', () => { currentDate.setMonth(currentDate.getMonth() - 1); renderCalendar(); });
    if ($('cal-next')) $('cal-next').addEventListener('click', () => { currentDate.setMonth(currentDate.getMonth() + 1); renderCalendar(); });
  });
})();
