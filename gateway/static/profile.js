(function() {
  const STORAGE_KEY = "bro.profile";
  const PROFILES = {
    generico:       { id:"generico",       assistant:"Bro",     icon:"🤙", name:"Generico",       skin:"ai",     greeting:"Come posso aiutarti?" },
    medico:         { id:"medico",         assistant:"Doc",     icon:"🩺", name:"Medico",         skin:"human",  greeting:"Pronto. Dimmi cosa ti serve." },
    avvocato:       { id:"avvocato",       assistant:"Avv",     icon:"⚖️", name:"Avvocato",       skin:"human",  greeting:"Dimmi il caso, lo analizziamo." },
    programmatore:  { id:"programmatore",  assistant:"Dev",     icon:"💻", name:"Programmatore",  skin:"ai",     greeting:"Pronto a scrivere codice." },
    insegnante:     { id:"insegnante",     assistant:"Prof",    icon:"📚", name:"Insegnante",     skin:"human",  greeting:"Prepariamo una lezione?" },
    artigiano:      { id:"artigiano",      assistant:"Mec",     icon:"🔧", name:"Artigiano",      skin:"ai",     greeting:"Cosa devi fare oggi?" },
    commercialista: { id:"commercialista", assistant:"Comm",    icon:"📊", name:"Commercialista", skin:"human",  greeting:"Pronto per i conti." },
    ricercatore:    { id:"ricercatore",    assistant:"Sci",     icon:"🔬", name:"Ricercatore",    skin:"alien",  greeting:"Cosa studiamo?" },
    cuoco:          { id:"cuoco",          assistant:"Chef",    icon:"👨‍🍳", name:"Cuoco",          skin:"fire",   greeting:"Cosa cuciniamo oggi?" },
    musicista:      { id:"musicista",      assistant:"Maestro", icon:"🎼", name:"Musicista",      skin:"ghost",  greeting:"Cosa creiamo?" }
  };
  function getProfile() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); }
    catch (e) { return null; }
  }
  function saveProfile(data) { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); }
  function clearProfile() { localStorage.removeItem(STORAGE_KEY); }
  function getCurrentProfile() {
    const saved = getProfile();
    if (!saved || !saved.profession) return null;
    const base = PROFILES[saved.profession] || PROFILES.generico;
    return { ...base, userName: saved.userName || "Utente", profession: saved.profession };
  }
  function isSetup() {
    const p = getProfile();
    return !!(p && p.userName && p.profession);
  }
  window.BroProfile = {
    PROFILES, getProfile, saveProfile, clearProfile, getCurrentProfile, isSetup,
    listProfessions() { return Object.values(PROFILES); }
  };
})();
