import { h } from '../dom.js';
import { DEVICE_TYPES } from '../deviceTypes.js';
import { findDevice, findRack, portsAbove, removeDevice, setLink, slugId } from '../model.js';
import { store, mutate } from '../store.js';
import { openDialog, confirmDialog, toast } from './overlay.js';
import { textField, selectField } from './fields.js';

function intInRange(field, min, max) {
  const v = Number(field.input.value);
  if (!Number.isInteger(v) || v < min || v > max) {
    field.setError(`Whole number from ${min} to ${max}`);
    return null;
  }
  field.setError('');
  return v;
}

function required(field) {
  const v = field.input.value.trim();
  field.setError(v ? '' : 'Required');
  return v || null;
}

// Add a device (deviceId omitted) or edit an existing one.
export function deviceDialog(deviceId) {
  const existing = deviceId ? findDevice(store.doc, deviceId) : null;
  const type = selectField({
    label: 'Type',
    value: existing?.type ?? 'switch',
    options: Object.entries(DEVICE_TYPES).map(([value, t]) => ({ value, label: t.label })),
  });
  const name = textField({ label: 'Name', value: existing?.name ?? '', placeholder: 'Switch 3' });
  const ports = textField({ label: 'Ports', type: 'number', value: existing?.ports ?? DEVICE_TYPES.switch.defaultPorts, min: 1, max: 512, mono: true });
  const note = textField({ label: 'Note', value: existing?.note ?? '', placeholder: 'Model, location, management IP…' });
  if (!existing) {
    type.input.addEventListener('change', () => { ports.input.value = DEVICE_TYPES[type.input.value].defaultPorts; });
  }

  const submit = async () => {
    const n = required(name);
    const count = intInRange(ports, 1, 512);
    if (!n || !count) return false;
    if (existing) {
      const lost = portsAbove(existing, count);
      if (lost.length && !(await confirmDialog('Shrink device',
        `${lost.length > 1 ? `Ports ${lost.join(', ')} hold` : `Port ${lost[0]} holds`} data that will be deleted. Continue?`, { danger: true, confirmLabel: 'Delete data' }))) return false;
      mutate((doc) => {
        for (const p of lost) setLink(doc, { device: deviceId, port: p }, null);
        const d = findDevice(doc, deviceId);
        Object.assign(d, { type: type.input.value, name: n, ports: count, note: note.input.value.trim() || undefined });
        for (const p of lost) delete d.port_data[String(p)];
      });
      toast(`${n} updated`, { kind: 'ok', timeout: 2000 });
    } else {
      mutate((doc) => {
        const id = slugId(n, new Set(doc.devices.map((d) => d.id)));
        doc.devices.push({ id, type: type.input.value, name: n, ports: count, note: note.input.value.trim() || undefined, port_data: {} });
      });
      toast(`${n} added`, { kind: 'ok', timeout: 2000 });
    }
    return true;
  };

  openDialog({
    title: existing ? `Edit ${existing.name}` : 'Add device',
    body: h('div', { class: 'dialog-fields' }, type.el, name.el, ports.el, note.el),
    actions: [{ label: 'Cancel' }, { label: existing ? 'Save' : 'Add device', kind: 'primary', onClick: submit }],
  });
}

export async function deleteDevice(deviceId) {
  const d = findDevice(store.doc, deviceId);
  if (!(await confirmDialog('Delete device', `Delete ${d.name} and everything stored on its ${d.ports} ports? Links to it are removed too.`,
    { danger: true, confirmLabel: 'Delete' }))) return;
  mutate((doc) => removeDevice(doc, deviceId));
  toast(`${d.name} deleted`, { kind: 'warn' });
}

// Add a rack (rackId omitted) or edit an existing one.
export function rackDialog(rackId) {
  const existing = rackId ? findRack(store.doc, rackId) : null;
  const taken = new Set(store.doc.racks.map((r) => r.id));
  const nextNum = store.doc.racks.length + 1;
  const id = textField({
    label: 'Rack code',
    value: existing?.id ?? `R${nextNum}`,
    mono: true,
    hint: 'Used in patch references, e.g. R1 in "R1 PP8 T05". Fixed once created.',
  });
  if (existing) id.input.disabled = true;
  const name = textField({ label: 'Name', value: existing?.name ?? `Rack ${nextNum}` });
  const panels = textField({ label: 'Patch panels', type: 'number', value: existing?.panels ?? 12, min: 1, max: 64, mono: true });
  const perPanel = textField({ label: 'Ports per panel', type: 'number', value: existing?.ports_per_panel ?? 24, min: 1, max: 96, mono: true });

  const submit = async () => {
    const n = required(name);
    const p = intInRange(panels, 1, 64);
    const pp = intInRange(perPanel, 1, 96);
    let code = existing?.id;
    if (!existing) {
      code = id.input.value.trim().toUpperCase();
      if (!/^R\d+$/.test(code)) { id.setError('R followed by a number, e.g. R3'); return false; }
      if (taken.has(code)) { id.setError('Already used'); return false; }
      id.setError('');
    }
    if (!n || !p || !pp) return false;
    if (existing) {
      const lost = Object.keys(existing.cells ?? {}).filter((k) => {
        const m = /^PP(\d+) T(\d+)$/.exec(k);
        return Number(m[1]) > p || Number(m[2]) > pp;
      });
      if (lost.length && !(await confirmDialog('Shrink rack', `${lost.length} patch positions hold data and will be deleted. Continue?`,
        { danger: true, confirmLabel: 'Delete data' }))) return false;
      mutate((doc) => {
        const r = findRack(doc, rackId);
        Object.assign(r, { name: n, panels: p, ports_per_panel: pp });
        for (const k of lost) delete r.cells[k];
      });
    } else {
      mutate((doc) => doc.racks.push({ id: code, name: n, panels: p, ports_per_panel: pp, cells: {} }));
    }
    toast(`${n} saved`, { kind: 'ok', timeout: 2000 });
    return true;
  };

  openDialog({
    title: existing ? `Edit ${existing.name}` : 'Add rack',
    body: h('div', { class: 'dialog-fields' }, id.el, name.el, h('div', { class: 'field-grid' }, panels.el, perPanel.el)),
    actions: [{ label: 'Cancel' }, { label: existing ? 'Save' : 'Add rack', kind: 'primary', onClick: submit }],
  });
}

export async function deleteRack(rackId) {
  const r = findRack(store.doc, rackId);
  if (!(await confirmDialog('Delete rack', `Delete ${r.name} and its patch-panel states? Desk records and port patch references are kept.`,
    { danger: true, confirmLabel: 'Delete' }))) return;
  mutate((doc) => { doc.racks = doc.racks.filter((x) => x.id !== rackId); });
  toast(`${r.name} deleted`, { kind: 'warn' });
}
