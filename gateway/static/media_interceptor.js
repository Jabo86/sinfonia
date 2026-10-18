(function () {
  var _originalFetch = window.fetch;
  var MEDIA_PATTERN = /(?:genera|crea|fai|disegna|produci|mostra)\s+(?:un['\s]*|una\s+)?(?:immagine|foto|disegno|illustrazione)\s+(?:di\s+|con\s+|che\s+(?:mostra|rappresenta)\s+)?(.+)/i;
  window.fetch = function (url, opts) {
    if (typeof url === 'string' && url.indexOf('/v1/chat/completions') !== -1 && opts && opts.body) {
      try {
        var body = JSON.parse(opts.body);
        var messages = body.messages || [];
        var lastUser = null;
        for (var i = messages.length - 1; i >= 0; i--) {
          if (messages[i].role === 'user') { lastUser = messages[i]; break; }
        }
        if (lastUser && typeof lastUser.content === 'string') {
          var m = lastUser.content.match(MEDIA_PATTERN);
          if (m) {
            var prompt = m[1].trim().replace(/[.!?]+$/, '');
            return _originalFetch('/v1/images/generations', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ prompt: prompt })
            }).then(async function (resp) {
              var j = await resp.json();
              var content;
              if (j.url) {
                content = '🖼️ Ecco l\'immagine che hai chiesto:\n\n![' + prompt + '](' + j.url + ')\n\n**Prompt:** ' + prompt + '\n**Provider:** ' + (j.provider || '?');
              } else if (j.detail) {
                content = '❌ Errore generazione immagine: ' + (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail));
              } else {
                content = '❌ Risposta inattesa dal generatore.';
              }
              return new Response(JSON.stringify({
                id: 'img-' + Date.now(),
                object: 'chat.completion',
                conversation_id: body.conversation_id || null,
                choices: [{ index: 0, message: { role: 'assistant', content: content }, finish_reason: 'stop' }]
              }), { status: 200, headers: { 'Content-Type': 'application/json' } });
            }).catch(function (e) {
              return new Response(JSON.stringify({
                choices: [{ index: 0, message: { role: 'assistant', content: '❌ Errore di rete: ' + e.message }, finish_reason: 'stop' }]
              }), { status: 200, headers: { 'Content-Type': 'application/json' } });
            });
          }
        }
      } catch (e) {}
    }
    return _originalFetch.apply(this, arguments);
  };
})();
