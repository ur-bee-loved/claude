import { h, icon, ICONS } from '../dom.js';
import { DEFAULT_STATE, countStates, findDuplicates, getPort, portMatches } from '../model.js';
import { deviceType } from '../deviceTypes.js';
import { store, toggleHiddenState } from '../store.js';
import { faceplate } from '../components/faceplate.js';
import { portCard } from '../components/portCard.js';
import { legend, stateBar } from '../components/legend.js';
import { deviceDialog, deleteDevice } from '../components/dialogs.js';
import { openPortEditor } from '../components/portEditor.js';

export const devicesView = {
  id: 'devices',
  label: 'Devices',
  icon: 'M3 7h18v10H3z M6 11h2v2H6z M10 11h2v2h-2z M14 11h2v2h-2z',
  render,
};

function render(root) {
  const { doc, ui } = store;
  const dupes = findDuplicates(doc);
  const dupeKeys = (deviceId, n) => {
    const keys = new Set();
    for (const key of ['ip', 'mac']) {
      const v = getPort(doc.devices.find((d) => d.id === deviceId), n)[key];
      if (v && dupes[key].has(v)) keys.add(key);
    }
    return keys;
  };

  root.append(h('div', { class: 'view-bar' },
    legend(doc, ui.hiddenStates, toggleHiddenState),
    h('button', { type: 'button', class: 'btn primary', onclick: () => deviceDialog() }, icon(ICONS.plus, 16), 'Add device')));

  if (!doc.devices.length) {
    root.append(h('div', { class: 'empty-state' },
      h('p', {}, 'No devices yet.'),
      h('button', { type: 'button', class: 'btn primary', onclick: () => deviceDialog() }, 'Add your first switch')));
    return;
  }

  for (const device of doc.devices) {
    const visible = (n) => !ui.hiddenStates.has(getPort(device, n).state) && portMatches(doc, device, n, ui.query);
    const counts = countStates(device);
    const inUse = device.ports - (counts[DEFAULT_STATE] ?? 0);
    const type = deviceType(device.type);

    const cards = [];
    for (let n = 1; n <= device.ports; n++) {
      if (visible(n)) cards.push(portCard(doc, device, n, { dupes: dupeKeys(device.id, n), onOpen: openPortEditor }));
    }

    root.append(h('section', { class: 'device-panel', 'aria-label': device.name },
      h('header', { class: 'device-head' },
        h('div', { class: 'device-id' },
          h('span', { class: 'device-icon' }, icon(type.icon, 22)),
          h('div', {},
            h('h2', { class: 'device-name' }, device.name),
            h('div', { class: 'device-sub' },
              h('span', {}, type.label.toUpperCase()),
              h('span', {}, `${device.ports} PORTS`),
              h('span', { class: 'accent' }, `${inUse} IN USE`),
              device.note && h('span', { class: 'muted' }, device.note)))),
        h('div', { class: 'device-actions' },
          h('button', { type: 'button', class: 'icon-btn', title: `Edit ${device.name}`, onclick: () => deviceDialog(device.id) }, icon(ICONS.edit)),
          h('button', { type: 'button', class: 'icon-btn danger', title: `Delete ${device.name}`, onclick: () => deleteDevice(device.id) }, icon(ICONS.trash)))),
      stateBar(doc, counts, device.ports),
      faceplate(doc, device, { isMatch: visible, onOpen: openPortEditor }),
      cards.length
        ? h('div', { class: 'port-grid' }, cards)
        : h('p', { class: 'muted no-match' }, 'No ports match the current search or filter.')));
  }
}
