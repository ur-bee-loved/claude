import { saveNetwork, ConflictError } from './api.js';

// Single source of truth for the page. Views read `store.doc` / `store.ui`,
// change data only through `mutate()`, and re-render when notified.

const SAVE_DELAY_MS = 400;

const listeners = new Set();
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
