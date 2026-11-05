import { saveNetwork, ConflictError } from './api.js';
import { loadPrefs, savePrefs } from './prefs.js';

// Single source of truth for the page. Views read `store.doc` / `store.ui`,
// change data only through `mutate()`, and re-render when notified.

const SAVE_DELAY_MS = 400;

const listeners = new Set();
const prefs = loadPrefs();
let saveTimer = null;
let saving = false;
let pending = false;

export const store = {
  doc: null,
  source: 'data',
  ui: {
    view: 'devices',
    query: '',
    hiddenStates: new Set(),
    expanded: prefs.expanded ?? {},
    portList: prefs.portList ?? {},
    saveStatus: 'saved',
    saveError: '',
  },
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function notify(kind) {
  for (const fn of listeners) fn(kind);
}

export function init(doc, source) {
  store.doc = doc;
  store.source = source;
  notify('doc');
}

export function setUi(patch) {
  Object.assign(store.ui, patch);
  notify('ui');
}

// Panels are keyed 'device:<id>' or 'rack:<id>'. Without a saved choice only
// the first panel of a view starts open.
export function isExpanded(key, index) {
  return store.ui.expanded[key] ?? index === 0;
}

export function setExpanded(keys, value) {
  const expanded = { ...store.ui.expanded };
  for (const k of keys) expanded[k] = value;
  setUi({ expanded });
  savePrefs({ expanded, portList: store.ui.portList });
}

export function togglePortList(deviceId) {
  const portList = { ...store.ui.portList, [deviceId]: !store.ui.portList[deviceId] };
  setUi({ portList });
  savePrefs({ expanded: store.ui.expanded, portList });
}

export function toggleHiddenState(id) {
  const hidden = new Set(store.ui.hiddenStates);
  if (hidden.has(id)) hidden.delete(id);
  else hidden.add(id);
  setUi({ hiddenStates: hidden });
}

export function mutate(fn) {
  fn(store.doc);
  notify('doc');
  scheduleSave();
}

// Replaces the document (JSON import) but keeps the server's revision so the save is accepted.
export function replaceDoc(doc) {
  doc.revision = store.doc.revision;
  store.doc = doc;
  notify('doc');
  scheduleSave();
}

function setStatus(saveStatus, saveError = '') {
  store.ui.saveStatus = saveStatus;
  store.ui.saveError = saveError;
  notify('status');
}

function scheduleSave() {
  clearTimeout(saveTimer);
  setStatus('pending');
  saveTimer = setTimeout(flush, SAVE_DELAY_MS);
}

export async function flush() {
  if (saving) {
    pending = true;
    return;
  }
  saving = true;
  setStatus('saving');
  try {
    const { revision } = await saveNetwork(store.doc);
    store.doc.revision = revision;
    store.source = 'data';
    setStatus('saved');
  } catch (err) {
    setStatus(err instanceof ConflictError ? 'conflict' : 'error', err.message);
  } finally {
    saving = false;
    if (pending) {
      pending = false;
      flush();
    }
  }
}
