import { h } from '../dom.js';
import { getPort, stateOf } from '../model.js';
import { deviceType } from '../deviceTypes.js';
import { pad } from './portCard.js';

const GROUP = 6;

// Compact front-panel drawing of a device. Each port is a button that opens
// the same editor as its card; hovering highlights the matching card.
export function faceplate(doc, device, { isMatch, onOpen }) {
  const layout = deviceType(device.type).layout;
  const rows = layout === 'odd-even' && device.ports > 1 ? 2 : 1;
  const cols = Math.ceil(device.ports / rows);

  const jack = (n) => {
    const port = getPort(device, n);
    const state = stateOf(doc, port.state);
    return h('button', {
      type: 'button',
      class: `jack${isMatch(n) ? '' : ' dim'}`,
      title: `${pad(n)} · ${state.label}${port.name ? ` · ${port.name}` : ''}`,
      dataset: { device: device.id, port: String(n), pattern: state.pattern ?? 'solid', row: rows === 2 ? (n % 2 ? 'top' : 'bottom') : 'top' },
      style: { '--state': state.color },
      onclick: () => onOpen(device.id, n),
      onmouseenter: () => highlight(device.id, n, true),
      onmouseleave: () => highlight(device.id, n, false),
    }, h('span', { class: 'jack-num' }, pad(n)));
  };

  const groups = [];
  for (let start = 0; start < cols; start += GROUP) {
    const groupCols = Math.min(GROUP, cols - start);
    const cells = [];
    for (let r = 0; r < rows; r++) {
      for (let c = start; c < start + groupCols; c++) {
        const n = rows === 2 ? c * 2 + 1 + r : c + 1;
        cells.push(n <= device.ports ? jack(n) : h('span', { class: 'jack ghost' }));
      }
    }
    groups.push(h('div', { class: 'jack-group', style: { '--cols': String(groupCols) } }, cells));
  }
  return h('div', { class: 'faceplate' },
    h('div', { class: 'faceplate-screws' }, h('span'), h('span')),
    h('div', { class: 'jack-groups' }, groups),
    h('div', { class: 'faceplate-leds' }, h('span', { class: 'led on' }), h('span', { class: 'led' })));
}

function highlight(deviceId, n, on) {
  const sel = `[data-device="${CSS.escape(deviceId)}"][data-port="${n}"]`;
  for (const el of document.querySelectorAll(sel)) el.classList.toggle('hot', on);
}
