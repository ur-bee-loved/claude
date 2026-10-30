import { h, icon, ICONS } from '../dom.js';
import { cellKey, endpointsAt, getCell, portsUsingPatch, stateOf } from '../model.js';
import { store, toggleHiddenState } from '../store.js';
import { legend } from '../components/legend.js';
import { rackDialog, deleteRack } from '../components/dialogs.js';
import { openCellEditor } from '../components/cellEditor.js';
import { endpointLabel } from '../components/portCard.js';

export const racksView = {
  id: 'racks',
  label: 'Racks',
  icon: ICONS.rack,
  render,
};

function cellMatches(doc, patch, cell, q) {
  if (!q) return true;
  const hay = [patch, cell.note, stateOf(doc, cell.state).label, ...endpointsAt(doc, patch).map(endpointLabel)];
  for (const r of portsUsingPatch(doc, patch)) {
    const d = doc.devices.find((x) => x.id === r.device);
    const p = d.port_data[String(r.port)];
    hay.push(d.name, p.name, p.ip, p.mac, p.connected);
  }
  return hay.some((v) => v && String(v).toLowerCase().includes(q));
}

function render(root) {
  const { doc, ui } = store;
  const q = ui.query.trim().toLowerCase();

  root.append(h('div', { class: 'view-bar' },
    legend(doc, ui.hiddenStates, toggleHiddenState),
    h('div', { class: 'rack-keys' },
      h('span', { class: 'key' }, h('i', { class: 'mark desk' }), 'Desk recorded'),
      h('span', { class: 'key' }, h('i', { class: 'mark wired' }), 'Wired to a device port')),
    h('button', { type: 'button', class: 'btn primary', onclick: () => rackDialog() }, icon(ICONS.plus, 16), 'Add rack')));

  if (!doc.racks.length) {
    root.append(h('div', { class: 'empty-state' }, h('p', {}, 'No racks yet.'),
      h('button', { type: 'button', class: 'btn primary', onclick: () => rackDialog() }, 'Add a rack')));
    return;
  }

  for (const rack of doc.racks) {
    const panels = [];
    let marked = 0;
    let withDesk = 0;
    for (let pp = 1; pp <= rack.panels; pp++) {
      const cells = [];
      for (let t = 1; t <= rack.ports_per_panel; t++) {
        const patch = `${rack.id} ${cellKey(pp, t)}`;
        const cell = getCell(rack, pp, t);
        const state = stateOf(doc, cell.state);
        const desks = endpointsAt(doc, patch);
        const wired = portsUsingPatch(doc, patch);
        if (cell.state !== 'available') marked++;
        if (desks.length) withDesk++;
        const show = !ui.hiddenStates.has(cell.state) && cellMatches(doc, patch, cell, q);
        const tip = [patch, state.label, ...desks.map(endpointLabel), ...wired.map((r) => {
          const d = doc.devices.find((x) => x.id === r.device);
          return `→ ${d.name} · ${String(r.port).padStart(2, '0')}`;
        }), cell.note].filter(Boolean).join('\n');
        cells.push(h('button', {
          type: 'button',
          class: `cell${show ? '' : ' dim'}${desks.length ? ' has-desk' : ''}${wired.length ? ' wired' : ''}`,
          title: tip,
          'aria-label': tip.replace(/\n/g, ', '),
          dataset: { pattern: state.pattern ?? 'solid' },
          style: { '--state': state.color },
          onclick: () => openCellEditor(rack.id, pp, t),
        }, h('span', { class: 'cell-num' }, String(t).padStart(2, '0'))));
      }
      panels.push(h('div', { class: 'panel-row' },
        h('span', { class: 'panel-label' }, `PP${pp}`),
        h('div', { class: 'panel-cells', style: { '--ports': String(rack.ports_per_panel) } }, cells)));
    }
    root.append(h('section', { class: 'device-panel rack-panel', 'aria-label': rack.name },
      h('header', { class: 'device-head' },
        h('div', { class: 'device-id' },
          h('span', { class: 'device-icon' }, icon(ICONS.rack, 22)),
          h('div', {},
            h('h2', { class: 'device-name' }, rack.name),
            h('div', { class: 'device-sub' },
              h('span', { class: 'mono' }, rack.id),
              h('span', {}, `${rack.panels} × ${rack.ports_per_panel}`),
              h('span', { class: 'accent' }, `${marked} MARKED`),
              h('span', {}, `${withDesk} WITH DESKS`)))),
        h('div', { class: 'device-actions' },
          h('button', { type: 'button', class: 'icon-btn', title: `Edit ${rack.name}`, onclick: () => rackDialog(rack.id) }, icon(ICONS.edit)),
          h('button', { type: 'button', class: 'icon-btn danger', title: `Delete ${rack.name}`, onclick: () => deleteRack(rack.id) }, icon(ICONS.trash)))),
      h('div', { class: 'rack-scroll' }, h('div', { class: 'rack-frame' }, panels))));
  }
}
