import { h, icon, ICONS } from '../dom.js';
import {
  ENDPOINT_FIELDS, cellKey, endpointsAt, findDevice, findRack, getCell, portsUsingPatch, setCell, stateOf,
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

  const stateField = selectField({
    label: 'Patch state',
    value: cell.state,
    options: doc.states.map((s) => ({ value: s.id, label: s.label })),
  });
  const note = textField({ label: 'Note', value: cell.note ?? '', multiline: true });

  // Desk rows are edited as a list; existing ones keep their position in doc.endpoints.
  const rows = endpointsAt(doc, patch).map((e) => ({ values: { ...e } }));
  const list = h('div', { class: 'endpoint-list' });
  const renderRows = () => {
    list.replaceChildren(...rows.map((row, i) => h('fieldset', { class: 'endpoint' },
      h('legend', {}, `Desk ${i + 1}`,
        h('button', { type: 'button', class: 'icon-btn small', title: 'Remove desk', onclick: () => { rows.splice(i, 1); renderRows(); } },
          icon(ICONS.trash, 14))),
      h('div', { class: 'field-grid three' }, ENDPOINT_FIELDS.map((f) => {
        const ui = textField({ label: f.label, value: row.values[f.key] ?? '' });
        ui.input.addEventListener('input', () => { row.values[f.key] = ui.input.value; });
        return ui.el;
      })))));
    if (!rows.length) list.append(h('p', { class: 'muted' }, 'No desk recorded for this patch position.'));
  };
  renderRows();

  const users = portsUsingPatch(doc, patch);
  const usedBy = users.length
    ? h('ul', { class: 'used-by' }, users.map((r) => {
      const d = findDevice(doc, r.device);
      return h('li', {}, h('button', { type: 'button', class: 'linkish', onclick: () => nav.openPort(r.device, r.port) },
        `${d.name} · port ${pad(r.port)}`));
    }))
    : h('p', { class: 'muted' }, 'No device port points at this patch. Set "Patch panel" on a port to connect it.');

  const save = () => {
    mutate((d) => {
      setCell(findRack(d, rackId), panel, port, { ...getCell(rack, panel, port), state: stateField.input.value, note: note.input.value.trim() });
      const kept = d.endpoints.filter((e) => e.patch !== patch);
      const edited = rows
        .map((r) => Object.fromEntries(Object.entries(r.values).map(([k, v]) => [k, typeof v === 'string' ? v.trim() : v])))
        .filter((v) => ENDPOINT_FIELDS.some((f) => v[f.key]))
        .map((v) => ({ ...v, patch }));
      d.endpoints = [...kept, ...edited];
    });
    closeDrawer();
    toast(`${patch} saved`, { kind: 'ok', timeout: 2000 });
  };

  openDrawer({
    kicker: rack.name,
    title: patch,
    accent: state.color,
    body: [
      stateField.el,
      note.el,
      h('h3', { class: 'section-title' }, 'Device ports using it'),
      usedBy,
      h('h3', { class: 'section-title' }, 'Desks'),
      list,
      h('button', { type: 'button', class: 'btn ghost small', onclick: () => { rows.push({ values: { patch } }); renderRows(); } },
        icon(ICONS.plus, 14), 'Add desk'),
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
