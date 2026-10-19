(function() {
  const originalFetch = window.fetch;
  window.fetch = async function(url, options) {
    if (typeof url === 'string' && url.includes('/v1/chat/completions') && options && options.method === 'POST' && options.body) {
      try {
        const body = JSON.parse(options.body);
        const messages = body.messages || [];
        let lastUser = null;
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].role === 'user') { lastUser = messages[i].content; break; }
        }
        if (!lastUser) return originalFetch.apply(this, arguments);
        
        const text = lastUser.toLowerCase();
        const todayStr = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
        const makeResp = (msg) => new Response(JSON.stringify({ id: 'x', object: 'chat.completion', model: 'sinfonia/interceptor', choices: [{ index: 0, message: { role: 'assistant', content: msg }, finish_reason: 'stop' }], conversation_id: body.conversation_id || null }), { status: 200, headers: { 'Content-Type': 'application/json' } });

        // --- NEXUS ---
        if (text.includes('nexus') || text.includes('orchestratore')) {
          let lang = text.includes('rust') ? 'rust' : text.includes('javascript') ? 'javascript' : 'python';
          fetch('/v1/orchestrator/start', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_dir: '/Users/jabo86/sinfonia/workspaces/voce-' + lang, requirements: "Crea un file in " + lang, language: lang, clean: true })
          }).then(() => document.getElementById('orchestrator-btn')?.click());
          return makeResp("Fatto, Fabio. Avvio NEXUS in " + lang + ".");
        }

        // --- LEGGI CALENDARIO ---
        // Se contiene "calendario", "agenda", "impegni", "eventi" O "cosa devo fare"
        const isReadReq = /calendario|agenda|impegni|eventi|programma/.test(text) || /cosa (devo|ho) fare/.test(text) || /cosa ho (oggi|stasera)/.test(text);
        if (isReadReq) {
          const r = await originalFetch('/v1/calendar/list');
          const data = await r.json();
          const todayEv = (data.events || []).filter(e => e.date === todayStr());
          
          if (todayEv.length === 0) {
            return makeResp("Oggi non hai eventi in programma, Fabio. La tua giornata è libera.");
          }
          
          todayEv.sort((a,b) => (a.time||'99:99').localeCompare(b.time||'99:99'));
          let reply = "Oggi hai in programma: ";
          todayEv.forEach((e, i) => { 
            reply += `${e.title}${e.time ? ' alle ' + e.time : ''}`;
            if (i < todayEv.length - 2) reply += ", poi ";
            else if (i === todayEv.length - 2) reply += " e infine ";
          });
          reply += ".";
          return makeResp(reply);
        }

        // --- AGGIUNGI CALENDARIO ---
        const addKw = ['inserisci', 'aggiungi', 'crea', 'metti', 'ricordami', 'segnati', 'fissa'];
        const hasAdd = addKw.some(k => text.includes(k)) && (text.includes('evento') || text.includes('impegno') || text.includes('calendario'));
        if (hasAdd) {
          let timeMatch = lastUser.match(/(?:alle|ore)\s*(?:ore\s*)?(\d{1,2})[:.](\d{2})/i) || lastUser.match(/(\d{1,2})[:.](\d{2})/);
          let timeStr = timeMatch ? `${String(parseInt(timeMatch[1])).padStart(2,'0')}:${timeMatch[2]}` : null;
          let title = lastUser.replace(/(?:inserisci|aggiungi|crea|metti|ricordami|segnati|fissa)\s*(?:un\s+|il\s+|l')?(?:evento|impegno|appuntamento|in\s+calendario)?\s*/gi, '').replace(/(?:oggi|domani)\s*/gi, '').replace(/(?:alle|ore)\s*\d{1,2}[:.]\d{2}/gi, '').trim();
          if (!title || title.length < 3) title = lastUser;
          
          await originalFetch('/v1/calendar/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: title, date: todayStr(), time: timeStr, description: '', type: 'impegno' }) });
          document.dispatchEvent(new Event('refresh_calendar'));
          return makeResp(`Fatto, Fabio. Ho aggiunto in calendario: ${title} ${timeStr ? 'alle ' + timeStr : ''}.`);
        }
      } catch (e) { console.error("Interceptor error:", e); }
    }
    return originalFetch.apply(this, arguments);
  };
})();
