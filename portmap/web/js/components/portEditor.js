import { h, icon, ICONS } from '../dom.js';
import {
  PORT_FIELDS, chainFor, endpointsAt, findDevice, findRack, formatPatch, getCell, getPort,
  normalizeField, parsePatch, portsUsingPatch, setLink, setPort, stateOf,
} from '../model.js';
import { CONNECTED_KINDS, deviceType } from '../deviceTypes.js';
import { store, mutate } from '../store.js';
import { nav } from '../nav.js';
import { openDrawer, closeDrawer, confirmDialog, toast } from './overlay.js';
import { textField, selectField, checkField } from './fields.js';
import { pad, endpointLabel } from './portCard.js';

const SUGGESTIONS = { connected: CONNECTED_KINDS };

export function openPortEditor(deviceId, n) {
  const doc = store.doc;
  const device = findDevice(doc, deviceId);
  if (!device) return;
  const port = getPort(device, n);
  const state = stateOf(doc, port.state);

  const stateField = selectField({
    label: 'State',
    value: port.state,
    options: doc.states.map((s) => ({ value: s.id, label: s.label })),
  });
  const swatch = h('span', { class: 'state-swatch', style: { '--state': state.color } });
  stateField.el.querySelector('label').prepend(swatch);
  stateField.input.addEventListener('change', () => {
    swatch.style.setProperty('--state', stateOf(doc, stateField.input.value).color);
  });

  const critical = checkField({ label: 'Critical infrastructure', checked: port.critical });

  const fields = PORT_FIELDS.map((f) => ({
    def: f,
    ui: textField({
      label: f.label,
      value: port[f.key] ?? '',
      placeholder: f.placeholder,
      multiline: f.kind === 'textarea',
      mono: ['ip', 'mac', 'patch'].includes(f.kind),
      suggestions: SUGGESTIONS[f.suggestions],
    }),
  }));

  const others = doc.devices.filter((d) => d.id !== deviceId);
  const linkDevice = selectField({
    label: 'Linked to device',
    value: port.link?.device ?? '',
    options: [{ value: '', label: '— none —' }, ...others.map((d) => ({ value: d.id, label: d.name }))],
    hint: 'For cables between your own devices (uplinks). Both ends are updated.',
  });
  const linkPort = textField({ label: 'Port', type: 'number', value: port.link?.port ?? '', min: 1, mono: true });
  const syncLinkPort = () => {
    const target = findDevice(doc, linkDevice.input.value);
    linkPort.input.disabled = !target;
    linkPort.input.max = target ? target.ports : '';
  };
  linkDevice.input.addEventListener('change', syncLinkPort);
  syncLinkPort();

  const preview = h('div', { class: 'chain-preview' });
  const patchUi = fields.find((f) => f.def.key === 'patch').ui;
  const renderPreview = () => preview.replaceChildren(chainView(doc, device, n, patchUi.input.value));
  patchUi.input.addEventListener('input', renderPreview);
  renderPreview();

  const save = () => {
    const next = { state: stateField.input.value, critical: critical.input.checked, link: port.link };
    let ok = true;
    for (const { def, ui } of fields) {
      const r = normalizeField(def.kind, ui.input.value);
      ui.setError(r.error);
      if (r.error) ok = false;
      else next[def.key] = r.value;
    }
    let linkTarget = null;
    linkPort.setError('');
    if (linkDevice.input.value) {
      const target = findDevice(doc, linkDevice.input.value);
      const p = Number(linkPort.input.value);
      if (!Number.isInteger(p) || p < 1 || p > target.ports) {
        linkPort.setError(`1 to ${target.ports}`);
        ok = false;
      } else linkTarget = { device: target.id, port: p };
    }
    if (!ok) return;
    const linkChanged = linkTarget?.device !== port.link?.device || linkTarget?.port !== port.link?.port;
    mutate((d) => {
      const dev = findDevice(d, deviceId);
      setPort(dev, n, next);
      if (linkChanged) setLink(d, { device: deviceId, port: n }, linkTarget);
    });
    closeDrawer();
    toast(`${device.name} · port ${pad(n)} saved`, { kind: 'ok', timeout: 2000 });
  };

  const clearPort = async () => {
    if (!(await confirmDialog('Clear port', `Remove every value stored for ${device.name} port ${pad(n)}?`, { danger: true, confirmLabel: 'Clear' }))) return;
    mutate((d) => {
      setLink(d, { device: deviceId, port: n }, null);
      setPort(findDevice(d, deviceId), n, {});
    });
    closeDrawer();
  };

  const step = (delta) => {
    const m = n + delta;
    if (m >= 1 && m <= device.ports) openPortEditor(deviceId, m);
  };

  openDrawer({
    kicker: `${deviceType(device.type).label} · ${device.name}`,
    title: `Port ${pad(n)}`,
    accent: state.color,
    body: [
      h('div', { class: 'field-grid' }, stateField.el, critical.el),
      fields.map((f) => f.ui.el),
      h('div', { class: 'field-grid link-grid' }, linkDevice.el, linkPort.el),
      h('h3', { class: 'section-title' }, 'Connection chain'),
      preview,
    ],
    footer: [
      h('div', { class: 'foot-left' },
        h('button', { type: 'button', class: 'icon-btn', title: 'Previous port', disabled: n <= 1, onclick: () => step(-1) }, '◀'),
        h('button', { type: 'button', class: 'icon-btn', title: 'Next port', disabled: n >= device.ports, onclick: () => step(1) }, '▶'),
        h('button', { type: 'button', class: 'btn danger ghost', onclick: clearPort }, icon(ICONS.trash, 15), 'Clear')),
      h('div', { class: 'foot-right' },
        h('button', { type: 'button', class: 'btn ghost', onclick: closeDrawer }, 'Cancel'),
        h('button', { type: 'button', class: 'btn primary', onclick: save }, 'Save')),
    ],
    onSubmit: save,
  });
}

// Device port -> link -> patch-panel cell -> desk. Uses the patch text being
// typed so the preview follows the input before it is saved.
function chainView(doc, device, n, patchText) {
  const chain = chainFor(doc, device.id, n);
  const p = parsePatch(patchText);
  const steps = [h('li', { class: 'step' }, h('span', { class: 'step-k' }, 'PORT'), h('span', {}, `${device.name} · ${pad(n)}`))];

  if (chain.link) {
    steps.push(h('li', { class: 'step' }, h('span', { class: 'step-k' }, 'LINK'),
      h('button', { type: 'button', class: 'linkish', onclick: () => nav.openPort(chain.link.device.id, chain.link.port) },
        `${chain.link.device.name} · ${pad(chain.link.port)}`)));
  }

  if (!p) {
    steps.push(h('li', { class: 'step muted' }, h('span', { class: 'step-k' }, 'PATCH'), h('span', {}, patchText.trim() ? 'Not a valid patch reference' : 'No patch panel set')));
    return h('ol', { class: 'chain' }, steps);
  }

  const patch = formatPatch(p);
  const rack = findRack(doc, p.rack);
  const inRange = rack && p.panel <= rack.panels && p.port <= rack.ports_per_panel;
  const cell = inRange ? getCell(rack, p.panel, p.port) : null;
  const cs = cell && stateOf(doc, cell.state);
  steps.push(h('li', { class: 'step', style: cs ? { '--state': cs.color } : null },
    h('span', { class: 'step-k' }, 'PATCH'),
    inRange
      ? h('button', { type: 'button', class: 'linkish', onclick: () => nav.openCell(p.rack, p.panel, p.port) }, patch)
      : h('span', { class: 'warn-text' }, `${patch} — ${rack ? 'outside the rack size' : `no rack "${p.rack}"`}`),
    cs && h('span', { class: 'tag', style: { '--state': cs.color } }, cs.label)));

  const sharing = portsUsingPatch(doc, patch).filter((r) => !(r.device === device.id && r.port === n));
  for (const r of sharing) {
    const d = findDevice(doc, r.device);
    steps.push(h('li', { class: 'step warn' }, h('span', { class: 'step-k' }, 'ALSO'),
      h('button', { type: 'button', class: 'linkish', onclick: () => nav.openPort(r.device, r.port) }, `${d.name} · ${pad(r.port)} uses this patch too`)));
  }

  const eps = endpointsAt(doc, patch);
  if (!eps.length) steps.push(h('li', { class: 'step muted' }, h('span', { class: 'step-k' }, 'DESK'), h('span', {}, 'No desk recorded for this patch')));
  for (const e of eps) {
    steps.push(h('li', { class: 'step' }, h('span', { class: 'step-k' }, 'DESK'),
      h('span', {}, endpointLabel(e)),
      e.cabling && h('span', { class: 'tag plain' }, e.cabling)));
  }
  return h('ol', { class: 'chain' }, steps);
}
