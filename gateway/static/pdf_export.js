/* ============================================================
   BRO — Export PDF conversazione
   Usa jsPDF (client-side, zero server)
   ============================================================ */
(function() {
  function exportPDF() {
    const { jsPDF } = window.jspdf || {};
    if (!jsPDF) {
      alert("jsPDF non caricato. Controlla la connessione.");
      return;
    }

    const messages = document.querySelectorAll("#messages .msg");
    if (messages.length === 0) {
      alert("Nessun messaggio da esportare.");
      return;
    }

    const doc = new jsPDF({ unit: "mm", format: "a4" });
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const margin = 15;
    const maxWidth = pageWidth - 2 * margin;
    let y = margin;

    // Header
    doc.setFillColor(0, 20, 10);
    doc.rect(0, 0, pageWidth, 25, "F");
    doc.setTextColor(0, 255, 136);
    doc.setFontSize(18);
    doc.setFont("helvetica", "bold");
    doc.text("BRO — Conversazione", margin, 15);
    doc.setFontSize(9);
    doc.setTextColor(200, 255, 224);
    const now = new Date().toLocaleString("it-IT");
    doc.text("Esportato: " + now, pageWidth - margin, 15, { align: "right" });
    y = 35;

    // Messages
    doc.setTextColor(30, 30, 30);
    for (const msg of messages) {
      const isUser = msg.classList.contains("user");
      const body = msg.querySelector(".msg-body");
      if (!body) continue;
      let text = body.innerText.trim();
      if (!text) continue;
      // Pulisci
      text = text.replace(/\s+/g, " ");

      const label = isUser ? "TU" : "BRO";
      const labelColor = isUser ? [0, 100, 50] : [80, 80, 80];

      // Etichetta
      doc.setFontSize(9);
      doc.setTextColor(labelColor[0], labelColor[1], labelColor[2]);
      doc.setFont("helvetica", "bold");
      if (y > pageHeight - 30) { doc.addPage(); y = 20; }
      doc.text(label, margin, y);
      y += 5;

      // Testo
      doc.setFontSize(10);
      doc.setTextColor(30, 30, 30);
      doc.setFont("helvetica", "normal");
      const lines = doc.splitTextToSize(text, maxWidth);
      for (const line of lines) {
        if (y > pageHeight - 20) { doc.addPage(); y = 20; }
        doc.text(line, margin, y);
        y += 5;
      }
      y += 3;
    }

    // Salva
    const filename = "bro-conversazione-" + new Date().toISOString().slice(0, 10) + ".pdf";
    doc.save(filename);
  }

  function init() {
    const btn = document.getElementById("export-pdf-btn");
    if (btn) btn.onclick = exportPDF;
    console.log("OK: PDF export pronto");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
