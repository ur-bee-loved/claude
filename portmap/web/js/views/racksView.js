import { h, icon, ICONS } from '../dom.js';
import { cellKey, endpointsAt, findDevice, getCell, portsUsingPatch, stateOf } from '../model.js';
import { store, isExpanded, toggleHiddenState } from '../store.js';
import { legend, stateBar } from '../components/legend.js';
import { collapsiblePanel, foldAllButtons } from '../components/panel.js';
import { hoverable } from '../components/hoverCard.js';
import { rackDialog, deleteRack } from '../components/dialogs.js';
import { openCellEditor } from '../components/cellEditor.js';
import { endpointLabel, pad } from '../components/portCard.js';

export const racksView = {
  id: 'racks',
  label: 'Racks',
  icon: ICONS.rack,
  render,
};

const stop = (fn) => (e) => {
  e.stopPropagation();
  fn();
};

function cellMatches(doc, patch, cell, q) {
  if (!q) return true;
  const hay = [patch, cell.note, stateOf(doc, cell.state).label, ...endpointsAt(doc, patch).map(endpointLabel)];
  for (const r of portsUsingPatch(doc, patch)) {
    const d = findDevice(doc, r.device);
    const p = d.port_data[String(r.port)];
    hay.push(d.name, p.name, p.ip, p.mac, p.connected);
  }
  return hay.some((v) => v && String(v).toLowerCase().includes(q));
}

function cellSummary(doc, patch, cell, desks, wired) {
  const state = stateOf(doc, cell.state);
  return {
    accent: state.color,
    content: h('div', {},
      h('div', { class: 'hc-head' },
        h('span', { class: 'hc-num' }, patch),
        h('span', { class: 'tag', style: { '--state': state.color } }, state.label)),
      wired.length > 0 && h('div', { class: 'hc-trails' }, wired.map((r) => {
        const d = findDevice(doc, r.device);
        const name = d.port_data[String(r.port)]?.name;
        return h('div', { class: 'hc-trail link' }, icon(ICONS.link, 13), `${d.name} · ${pad(r.port)}${name ? ` · ${name}` : ''}`);
      })),
      desks.length > 0 && h('div', { class: 'hc-trails' }, desks.map((e) =>
        h('div', { class: 'hc-trail' }, icon(ICONS.arrow, 13), endpointLabel(e), e.cabling && h('span', { class: 'tag plain' }, e.cabling)))),
      !wired.length && !desks.length && h('div', { class: 'hc-sub muted' }, 'No device port or desk recorded'),
      cell.note && h('div', { class: 'hc-note' }, cell.note),
      h('div', { class: 'hc-hint' }, 'Click to edit')),
  };
}

function render(root) {
  const { doc, ui } = store;
  const q = ui.query.trim().toLowerCase();

  root.append(h('div', { class: 'view-bar' },
    legend(doc, ui.hiddenStates, toggleHiddenState),
    h('div', { class: 'rack-keys' },
      h('span', { class: 'key' }, h('i', { class: 'mark desk' }), 'Desk recorded'),
      h('span', { class: 'key' }, h('i', { class: 'mark wired' }), 'Wired to a device port')),
    h('div', { class: 'view-actions' },
      doc.racks.length > 1 && foldAllButtons(doc.racks.map((r) => `rack:${r.id}`)),
      h('button', { type: 'button', class: 'btn primary', onclick: () => rackDialog() }, icon(ICONS.plus, 16), 'Add rack'))));

  if (!doc.racks.length) {
    root.append(h('div', { class: 'empty-state' }, h('p', {}, 'No racks yet.'),
      h('button', { type: 'button', class: 'btn primary', onclick: () => rackDialog() }, 'Add a rack')));
    return;
  }

  doc.racks.forEach((rack, index) => {
    const counts = {};
    let withDesk = 0;
    let hits = 0;
    const panels = [];
    for (let pp = 1; pp <= rack.panels; pp++) {
      const cells = [];
      for (let t = 1; t <= rack.ports_per_panel; t++) {
        const patch = `${rack.id} ${cellKey(pp, t)}`;
        const cell = getCell(rack, pp, t);
        const state = stateOf(doc, cell.state);
        const desks = endpointsAt(doc, patch);
        const wired = portsUsingPatch(doc, patch);
        counts[cell.state] = (counts[cell.state] ?? 0) + 1;
        if (desks.length) withDesk++;
        const show = !ui.hiddenStates.has(cell.state) && cellMatches(doc, patch, cell, q);
        if (q && show) hits++;
        const el = h('button', {
          type: 'button',
          class: `cell${show ? '' : ' dim'}${desks.length ? ' has-desk' : ''}${wired.length ? ' wired' : ''}`,
          'aria-label': `${patch}, ${state.label}${desks.length ? `, ${desks.map(endpointLabel).join('; ')}` : ''}`,
          dataset: { pattern: state.pattern ?? 'solid' },
          style: { '--state': state.color },
          onclick: () => openCellEditor(rack.id, pp, t),
        }, h('span', { class: 'cell-num' }, pad(t)));
        hoverable(el, () => cellSummary(doc, patch, cell, desks, wired));
        cells.push(el);
      }
      panels.push(h('div', { class: 'panel-row' },
        h('span', { class: 'panel-label' }, `PP${pp}`),
        h('div', { class: 'panel-cells', style: { '--ports': String(rack.ports_per_panel) } }, cells)));
    }
    const total = rack.panels * rack.ports_per_panel;
    const marked = total - (counts.available ?? 0);
    const key = `rack:${rack.id}`;
    const open = q ? hits > 0 : isExpanded(key, index);

    root.append(collapsiblePanel({
      key,
      open,
      iconPath: ICONS.rack,
      title: rack.name,
      className: `rack-panel${q && !hits ? ' no-hits' : ''}`,
      sub: [
        h('span', { class: 'mono' }, rack.id),
        h('span', {}, `${rack.panels} × ${rack.ports_per_panel}`),
        h('span', { class: 'accent' }, `${marked} MARKED`),
        h('span', {}, `${withDesk} WITH DESKS`),
        q && h('span', { class: 'hits' }, `${hits} MATCH${hits === 1 ? '' : 'ES'}`),
      ],
      bar: stateBar(doc, counts, total),
      actions: [
        h('button', { type: 'button', class: 'icon-btn', title: `Edit ${rack.name}`, onclick: stop(() => rackDialog(rack.id)) }, icon(ICONS.edit)),
        h('button', { type: 'button', class: 'icon-btn danger', title: `Delete ${rack.name}`, onclick: stop(() => deleteRack(rack.id)) }, icon(ICONS.trash)),
      ],
      body: () => h('div', { class: 'rack-scroll' }, h('div', { class: 'rack-frame' }, panels)),
    }));
  });
}
