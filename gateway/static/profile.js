const PROFILES = [
  { id: "sinfonia", name: "Sinfonia", icon: "🎼", profession: "Assistente universale" }
];
window.BroProfile = {
  getCurrentProfile: () => PROFILES[0],
  getProfiles: () => PROFILES
};
