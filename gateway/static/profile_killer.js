(function() {
  // 1. Intercetta la chiamata al backend che restituisce i profili
  const originalFetch = window.fetch;
  window.fetch = async function(url, options) {
    if (typeof url === 'string' && url.includes('/v1/professions')) {
      return new Response(JSON.stringify({
        professions: [{ id: "sinfonia", name: "Sinfonia", icon: "🎼", profession: "Assistente universale" }]
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return originalFetch.apply(this, arguments);
  };

  // 2. Guardiano che elimina fisicamente i profili indesiderati dal DOM
  function cleanProfiles() {
    // Pulisce il menu a tendina in alto
    const dropdown = document.getElementById('prof-dropdown');
    if (dropdown) {
      Array.from(dropdown.children).forEach(child => {
        if (!child.textContent.includes('Sinfonia') && child.textContent.trim() !== '') {
          child.remove();
        }
      });
    }
    
    // Pulisce la griglia nell'onboarding
    const grid = document.getElementById('prof-grid');
    if (grid) {
      Array.from(grid.children).forEach((child, index) => {
        if (index !== 0) child.remove();
      });
    }
  }

  // Esegui subito
  cleanProfiles();

  // Esegui ogni volta che la pagina cambia (se app.js li reinserisce)
  const observer = new MutationObserver(cleanProfiles);
  observer.observe(document.body, { childList: true, subtree: true });
  
  // Esegui anche ogni secondo per sicurezza
  setInterval(cleanProfiles, 1000);
})();
