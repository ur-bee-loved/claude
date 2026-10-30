// Cross-view navigation, filled in by main.js. Components call these instead of
// importing each other, which keeps the module graph free of cycles.
export const nav = {
  openPort: (deviceId, n) => {},
  openCell: (rackId, panel, port) => {},
  setView: (id) => {},
};
