import { h, icon, ICONS } from '../dom.js';
import { DEFAULT_STATE, countStates, findDuplicates, getPort, portMatches } from '../model.js';
import { deviceType } from '../deviceTypes.js';
import { store, isExpanded, toggleHiddenState, togglePortList } from '../store.js';
import { faceplate } from '../components/faceplate.js';
import { portCard } from '../components/portCard.js';
import { legend, stateBar } from '../components/legend.js';
import { collapsiblePanel, foldAllButtons } from '../components/panel.js';
import { deviceDialog, deleteDevice } from '../components/dialogs.js';
import { openPortEditor } from '../components/portEditor.js';

export const devicesView = {
  id: 'devices',
  label: 'Devices',
  icon: 'M3 7h18v10H3z M6 11h2v2H6z M10 11h2v2h-2z M14 11h2v2h-2z',
  render,
};

const stop = (fn) => (e) => {
  e.stopPropagation();
  fn();
};

function render(root) {
  const { doc, ui } = store;
  const searching = ui.query.trim() !== '';
  const dupes = findDuplicates(doc);
  const dupeKeys = (device, n) => {
    const keys = new Set();
    for (const key of ['ip', 'mac']) {
      const v = getPort(device, n)[key];
      if (v && dupes[key].has(v)) keys.add(key);
    }
    return keys;
  };

  root.append(h('div', { class: 'view-bar' },
    legend(doc, ui.hiddenStates, toggleHiddenState),
    h('div', { class: 'view-actions' },
      doc.devices.length > 1 && foldAllButtons(doc.devices.map((d) => `device:${d.id}`)),
      h('button', { type: 'button', class: 'btn primary', onclick: () => deviceDialog() }, icon(ICONS.plus, 16), 'Add device'))));

  if (!doc.devices.length) {
    root.append(h('div', { class: 'empty-state' },
      h('p', {}, 'No devices yet.'),
      h('button', { type: 'button', class: 'btn primary', onclick: () => deviceDialog() }, 'Add your first switch')));
    return;
  }

  doc.devices.forEach((device, index) => {
    const visible = (n) => !ui.hiddenStates.has(getPort(device, n).state) && portMatches(doc, device, n, ui.query);
    const shown = [];
    for (let n = 1; n <= device.ports; n++) if (visible(n)) shown.push(n);
    const counts = countStates(device);
    const inUse = device.ports - (counts[DEFAULT_STATE] ?? 0);
    const type = deviceType(device.type);
    const key = `device:${device.id}`;
    const open = searching ? shown.length > 0 : isExpanded(key, index);
    const listOpen = Boolean(ui.portList[device.id]);

    root.append(collapsiblePanel({
      key,
      open,
      iconPath: type.icon,
      title: device.name,
      className: searching && !shown.length ? 'no-hits' : '',
      sub: [
        h('span', {}, type.label.toUpperCase()),
        h('span', {}, `${device.ports} PORTS`),
        h('span', { class: 'accent' }, `${inUse} IN USE`),
        searching && h('span', { class: 'hits' }, `${shown.length} MATCH${shown.length === 1 ? '' : 'ES'}`),
        device.note && h('span', { class: 'muted' }, device.note),
      ],
      bar: stateBar(doc, counts, device.ports),
      actions: [
        h('button', { type: 'button', class: 'icon-btn', title: `Edit ${device.name}`, onclick: stop(() => deviceDialog(device.id)) }, icon(ICONS.edit)),
        h('button', { type: 'button', class: 'icon-btn danger', title: `Delete ${device.name}`, onclick: stop(() => deleteDevice(device.id)) }, icon(ICONS.trash)),
      ],
      body: () => [
        faceplate(doc, device, { isMatch: visible, onOpen: openPortEditor }),
        h('div', { class: 'panel-tools' },
          h('span', { class: 'muted hint' }, 'Hover a port for details · click it to edit'),
          h('button', {
            type: 'button',
            class: `btn ghost small${listOpen ? ' on' : ''}`,
            'aria-pressed': String(listOpen),
            onclick: () => togglePortList(device.id),
          }, icon(ICONS.list, 14), listOpen ? 'Hide port list' : `Show port list (${shown.length})`)),
        listOpen && (shown.length
          ? h('div', { class: 'port-grid' }, shown.map((n) => portCard(doc, device, n, { dupes: dupeKeys(device, n), onOpen: openPortEditor })))
          : h('p', { class: 'muted no-match' }, 'No ports match the current search or filter.')),
      ],
    }));
  });
}
