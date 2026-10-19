(function() {
  // Questa funzione viene eseguita ogni 500ms. Se trova "Sinfonia", lo cambia in "ULTRON".
  setInterval(() => {
    // 1. Titolo della pagina
    if (document.title.includes('Sinfonia')) {
      document.title = 'ULTRON — Assistente AI';
    }
    
    // 2. Logo nella sidebar
    const logo = document.querySelector('.logo-name');
    if (logo && logo.innerText.trim() !== 'ULTRON') {
      logo.innerText = 'ULTRON';
    }
    
    // 3. Barra di scrittura in basso
    const input = document.getElementById('input');
    if (input && input.placeholder.includes('Sinfonia')) {
      input.placeholder = 'Scrivi un messaggio a ULTRON...';
    }
    
    // 4. Testo di errore in basso
    const hint = document.querySelector('.composer-hint');
    if (hint && hint.innerText.includes('Sinfonia')) {
      hint.innerText = 'ULTRON può commettere errori · Verifica le informazioni importanti';
    }
  }, 500);
})();
