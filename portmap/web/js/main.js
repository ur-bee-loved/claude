import { h, clear, icon, ICONS } from './dom.js';
import { loadNetwork } from './api.js';
import { store, init, subscribe, setUi, replaceDoc, flush } from './store.js';
import { nav } from './nav.js';
import { closeDrawer, isDrawerOpen, confirmDialog, toast } from './components/overlay.js';
import { openPortEditor } from './components/portEditor.js';
import { openCellEditor } from './components/cellEditor.js';
import { devicesView } from './views/devicesView.js';
import { racksView } from './views/racksView.js';

// To add a view, write a module exporting { id, label, icon, render(root) }
// and list it here. It gets a tab and a #hash route.
const VIEWS = [devicesView, racksView];

const $ = (id) => document.getElementById(id);

function currentView() {
  return VIEWS.find((v) => v.id === store.ui.view) ?? VIEWS[0];
}

function renderTabs() {
  clear($('tabs')).append(...VIEWS.map((v) => h('a', {
    href: `#${v.id}`,
    class: `tab${v.id === store.ui.view ? ' active' : ''}`,
    'aria-current': v.id === store.ui.view ? 'page' : null,
  }, icon(v.icon, 16), v.label)));
}

function renderView() {
  const root = $('view');
  const y = window.scrollY;
  clear(root);
  currentView().render(root);
  window.scrollTo(0, y);
}

const STATUS_TEXT = {
  saved: 'SYNCED',
  pending: 'EDITED',
  saving: 'SAVING',
  error: 'SAVE FAILED',
  conflict: 'CONFLICT',
};

function renderStatus() {
  const { saveStatus, saveError } = store.ui;
  const el = $('status');
  el.dataset.status = saveStatus;
  el.title = saveError || (saveStatus === 'saved' ? `Saved to the server (revision ${store.doc.revision ?? 0})` : '');
  el.textContent = STATUS_TEXT[saveStatus];
  if (saveStatus === 'error') {
    toast(`Not saved: ${saveError}`, { kind: 'error', timeout: 0, action: { label: 'Retry', onClick: flush } });
  } else if (saveStatus === 'conflict') {
    toast('The data file changed elsewhere (another tab or an import). Reload to continue; your last edit is not saved.',
      { kind: 'error', timeout: 0, action: { label: 'Reload', onClick: () => location.reload() } });
  }
}

function renderBanner() {
  const el = $('banner');
  el.hidden = store.source !== 'example';
  if (!el.hidden) {
    clear(el).append(
      h('strong', {}, 'EXAMPLE DATA'),
      h('span', {}, ' — data/network.json does not exist yet. Run ', h('code', {}, 'python3 import_xlsx.py your.xlsx'),
        ' to load your spreadsheet, or edit here: the first change creates the file.'));
  }
}

function exportJson() {
  const blob = new Blob([JSON.stringify(store.doc, null, 2)], { type: 'application/json' });
  const a = h('a', { href: URL.createObjectURL(blob), download: `portmap-${new Date().toISOString().slice(0, 10)}.json` });
  a.click();
  URL.revokeObjectURL(a.href);
}

async function importJson(file) {
  let doc;
  try {
    doc = JSON.parse(await file.text());
    if (!Array.isArray(doc.devices) || !Array.isArray(doc.racks) || !Array.isArray(doc.states)) throw new Error('missing devices, racks or states');
  } catch (err) {
    toast(`Cannot import ${file.name}: ${err.message}`, { kind: 'error' });
    return;
  }
  if (!(await confirmDialog('Import JSON', `Replace all current data with ${file.name}? The server keeps a backup of the current file.`,
    { danger: true, confirmLabel: 'Replace' }))) return;
  doc.endpoints ??= [];
  replaceDoc(doc);
  toast(`Imported ${file.name}`, { kind: 'ok' });
}

function flashCard(deviceId, n) {
  const el = document.querySelector(`.port-card[data-device="${CSS.escape(deviceId)}"][data-port="${n}"]`);
  if (!el) return;
  el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 1400);
}

function wireNav() {
  // pushState does not fire hashchange, so the drawer opened right after stays open.
  nav.setView = (id) => {
    if (store.ui.view === id) return;
    history.pushState(null, '', `#${id}`);
    setUi({ view: id });
  };
  nav.openPort = (deviceId, n) => {
    nav.setView('devices');
    requestAnimationFrame(() => {
      if (!store.ui.hiddenStates.size && !store.ui.query) flashCard(deviceId, n);
      openPortEditor(deviceId, n);
    });
  };
  nav.openCell = (rackId, panel, port) => {
    nav.setView('racks');
    requestAnimationFrame(() => openCellEditor(rackId, panel, port));
  };
}

function wireHeader() {
  const search = $('search');
  search.addEventListener('input', () => setUi({ query: search.value }));
  $('export').addEventListener('click', exportJson);
  $('import').addEventListener('click', () => $('import-file').click());
  $('import-file').addEventListener('change', (e) => {
    const f = e.target.files[0];
    e.target.value = '';
    if (f) importJson(f);
  });

  document.addEventListener('keydown', (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName ?? '');
    if (e.key === '/' && !typing) {
      e.preventDefault();
      search.focus();
      search.select();
    } else if (e.key === 'Escape' && isDrawerOpen() && !document.querySelector('dialog[open]')) {
      closeDrawer();
    } else if (e.key === 'Escape' && document.activeElement === search && search.value) {
      search.value = '';
      setUi({ query: '' });
    }
  });

  window.addEventListener('beforeunload', (e) => {
    if (['pending', 'saving', 'error'].includes(store.ui.saveStatus)) e.preventDefault();
  });
}

function syncRoute() {
  const id = location.hash.slice(1);
  const view = VIEWS.find((v) => v.id === id) ?? VIEWS[0];
  closeDrawer();
  setUi({ view: view.id });
}

async function main() {
  wireNav();
  wireHeader();
  subscribe((kind) => {
    if (kind === 'status') return renderStatus();
    renderTabs();
    renderView();
    renderBanner();
  });
  window.addEventListener('hashchange', syncRoute);
  try {
    const { doc, source } = await loadNetwork();
    store.ui.view = (VIEWS.find((v) => v.id === location.hash.slice(1)) ?? VIEWS[0]).id;
    init(doc, source);
    renderStatus();
    $('site').textContent = doc.site || 'Network';
  } catch (err) {
    clear($('view')).append(h('div', { class: 'empty-state error' },
      h('p', {}, `Could not load the network data: ${err.message}`),
      h('p', { class: 'muted' }, 'Start the app with "python3 server.py" and open the address it prints.')));
  }
}

main();
