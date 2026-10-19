const DEFAULT_PROFILE = { id: "ultron", name: "ULTRON", icon: "🤖", profession: "Assistente universale" };
window.BroProfile = {
  getCurrentProfile: () => DEFAULT_PROFILE,
  getProfiles: () => [DEFAULT_PROFILE],
  isSetup: () => true,
  saveProfile: () => {},
  reset: () => {},
  setProfile: () => {}
};
