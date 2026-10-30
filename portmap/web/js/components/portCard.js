import { h, icon, ICONS } from '../dom.js';
import { PORT_FIELDS, chainFor, stateOf } from '../model.js';

export function pad(n) {
  return String(n).padStart(2, '0');
}

export function endpointLabel(e) {
  return [e.setor, e.referencia, e.baia && `Baia ${e.baia}`, e.letra].filter(Boolean).join(' · ');
}

const META_LABELS = { ip: 'IP', mac: 'MAC', patch: 'PATCH' };

// dupes: Set of field keys ('ip', 'mac') that are shared with another port.
export function portCard(doc, device, n, { dupes, onOpen }) {
  const chain = chainFor(doc, device.id, n);
  const port = chain.port;
  const state = stateOf(doc, port.state);
  const empty = !port.name && !port.connected;

  const metaRows = PORT_FIELDS.filter((f) => f.card && META_LABELS[f.key]).map((f) =>
    h('div', { class: `pc-row${dupes.has(f.key) ? ' dupe' : ''}` },
      h('span', { class: 'pc-key' }, META_LABELS[f.key]),
      h('span', { class: `pc-val mono${port[f.key] ? '' : ' nil'}` }, port[f.key] || '—'),
      dupes.has(f.key) && h('span', { class: 'pc-flag', title: `This ${META_LABELS[f.key]} is also used by another port` }, icon(ICONS.warn, 13))));

  const trail = [];
  if (chain.link) {
    trail.push(h('div', { class: 'pc-trail link' }, icon(ICONS.link, 13),
      h('span', {}, `${chain.link.device.name} · ${pad(chain.link.port)}`)));
  }
  for (const e of chain.endpoints) {
    trail.push(h('div', { class: 'pc-trail' }, icon(ICONS.arrow, 13), h('span', {}, endpointLabel(e))));
  }
  if (chain.cell && chain.cell.state !== port.state && chain.cell.state !== 'available') {
    const cs = stateOf(doc, chain.cell.state);
    trail.push(h('div', { class: 'pc-trail', style: { '--state': cs.color } },
      h('span', { class: 'dot' }), h('span', {}, `Patch: ${cs.label}`)));
  }

  const card = h('article', {
    class: `port-card${empty ? ' empty' : ''}`,
    tabindex: 0,
    role: 'button',
    'aria-label': `Port ${n}, ${state.label}${port.name ? `, ${port.name}` : ''}`,
    dataset: { device: device.id, port: String(n), pattern: state.pattern ?? 'solid' },
    style: { '--state': state.color },
    onclick: () => onOpen(device.id, n),
    onkeydown: (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onOpen(device.id, n);
      }
    },
  },
  h('div', { class: 'pc-head' },
    h('span', { class: 'pc-num' }, pad(n)),
    port.critical && h('span', { class: 'pc-crit', title: 'Critical' }, icon(ICONS.star, 13)),
    port.note && h('span', { class: 'pc-note', title: port.note }, 'NOTE'),
    h('span', { class: 'pc-state' }, state.label)),
  h('div', { class: `pc-name${port.name ? '' : ' nil'}` }, port.name || 'Unassigned'),
  h('div', { class: 'pc-connected' }, port.connected || ' '),
  h('div', { class: 'pc-meta' }, metaRows),
  trail.length > 0 && h('div', { class: 'pc-trails' }, trail));
  return card;
}
