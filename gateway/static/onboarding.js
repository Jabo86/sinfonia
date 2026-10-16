(function() {
  function show() {
    const overlay = document.getElementById("onboarding");
    if (!overlay) return;
    overlay.style.display = "flex";
    const grid = document.getElementById("prof-grid");
    grid.innerHTML = "";
    let selected = "generico";
    for (const p of window.BroProfile.listProfessions()) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "prof-card" + (p.id === selected ? " selected" : "");
      btn.dataset.prof = p.id;
      btn.innerHTML = '<div class="prof-icon">' + p.icon + '</div><div class="prof-info"><div class="prof-title">' + p.assistant + '</div><div class="prof-sub">' + p.name + '</div></div>';
      btn.onclick = function() {
        selected = p.id;
        document.querySelectorAll(".prof-card").forEach(function(c) { c.classList.remove("selected"); });
        btn.classList.add("selected");
      };
      grid.appendChild(btn);
    }
    document.getElementById("onboarding-form").onsubmit = function(e) {
      e.preventDefault();
      const userName = document.getElementById("onb-name").value.trim();
      if (!userName) { document.getElementById("onb-name").focus(); return; }
      window.BroProfile.saveProfile({ userName: userName, profession: selected, createdAt: Date.now() });
      overlay.style.display = "none";
      window.location.reload();
    };
    document.getElementById("onb-name").focus();
  }
  window.BroOnboarding = {
    show: show,
    showIfNeeded: function() {
      if (!window.BroProfile.isSetup()) { show(); return true; }
      return false;
    }
  };
})();
