// Per-browser view preferences (which panels are open). They are not network
// data, so they live in localStorage instead of the data file. Storage can be
// unavailable (private windows, blocked site data); the page then just starts
// from the defaults every time.

const KEY = 'portmap:ui:v1';

export function loadPrefs() {
  try {
    const value = JSON.parse(localStorage.getItem(KEY));
    return value && typeof value === 'object' ? value : {};
  } catch {
    return {};
  }
}

export function savePrefs(prefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // ignored: see above
  }
}
