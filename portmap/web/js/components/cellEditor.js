import { h } from '../dom.js';
import {
  CABLING_STATUSES, DEFAULT_CABLING, DESK_FIELDS, cellKey, deskAt, findDevice, findRack, getCell,
  portsUsingPatch, setCell, setDesk, stateOf,
} from '../model.js';
import { store, mutate } from '../store.js';
import { nav } from '../nav.js';
import { openDrawer, closeDrawer, toast } from './overlay.js';
import { textField, selectField } from './fields.js';
import { pad } from './portCard.js';

export function openCellEditor(rackId, panel, port) {
  const doc = store.doc;
  const rack = findRack(doc, rackId);
  if (!rack) return;
  const cell = getCell(rack, panel, port);
  const patch = `${rackId} ${cellKey(panel, port)}`;
  const state = stateOf(doc, cell.state);
  const desk = deskAt(doc, patch) ?? {};

  const stateField = selectField({
    label: 'Patch state',
    value: cell.state,
    options: doc.states.map((s) => ({ value: s.id, label: s.label })),
  });
  const note = textField({ label: 'Note', value: cell.note ?? '', multiline: true });

  // A patch position has exactly one place, so this is a fixed form, not a list.
  const deskFields = DESK_FIELDS.map((f) => ({
    key: f.key,
    ui: textField({ label: f.label, value: desk[f.key] ?? '', placeholder: f.placeholder }),
  }));
  const current = desk.cabling || DEFAULT_CABLING;
  const options = CABLING_STATUSES.map((c) => ({ value: c.id, label: c.label }));
  if (!options.some((o) => o.value === current)) options.push({ value: current, label: `${current} (unknown)` });
  const cabling = selectField({ label: 'Status infra cabeada', value: current, options });

  const users = portsUsingPatch(doc, patch);
  const usedBy = users.length
    ? h('ul', { class: 'used-by' }, users.map((r) => {
      const d = findDevice(doc, r.device);
      return h('li', {}, h('button', { type: 'button', class: 'linkish', onclick: () => nav.openPort(r.device, r.port) },
        `${d.name} · port ${pad(r.port)}`));
    }))
    : h('p', { class: 'muted' }, 'No device port points at this patch. Set "Patch panel" on a port to connect it.');

  const save = () => {
    const place = Object.fromEntries(deskFields.map(({ key, ui }) => [key, ui.input.value.trim()]));
    mutate((d) => {
      setCell(findRack(d, rackId), panel, port, { ...getCell(rack, panel, port), state: stateField.input.value, note: note.input.value.trim() });
      setDesk(d, patch, { ...place, cabling: cabling.input.value });
    });
    closeDrawer();
    toast(`${patch} saved`, { kind: 'ok', timeout: 2000 });
  };

  const [setor, mesa, baia, letra] = deskFields.map((f) => f.ui.el);
  openDrawer({
    kicker: rack.name,
    title: patch,
    accent: state.color,
    body: [
      stateField.el,
      note.el,
      h('h3', { class: 'section-title' }, 'Device ports using it'),
      usedBy,
      h('h3', { class: 'section-title' }, 'Desk'),
      h('p', { class: 'muted hint' }, 'The physical place this position leads to. One per position.'),
      h('div', { class: 'field-grid two' }, setor, mesa),
      h('div', { class: 'field-grid two' }, baia, letra),
      cabling.el,
    ],
    footer: [
      h('div', { class: 'foot-left' }),
      h('div', { class: 'foot-right' },
        h('button', { type: 'button', class: 'btn ghost', onclick: closeDrawer }, 'Cancel'),
        h('button', { type: 'button', class: 'btn primary', onclick: save }, 'Save')),
    ],
    onSubmit: save,
  });
}
