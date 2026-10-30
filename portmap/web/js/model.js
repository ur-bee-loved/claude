// Pure data functions: no DOM access, so they run in the browser and under `node --test`.

export const DEFAULT_STATE = 'available';

// Editable port fields. The editor and the port cards are both built from this
// list, so a new field only needs a new entry here.
export const PORT_FIELDS = [
  { key: 'name', label: 'Reference name', kind: 'text', card: true },
  { key: 'connected', label: 'Connected device', kind: 'text', card: true, suggestions: 'connected' },
  { key: 'ip', label: 'IP address', kind: 'ip', card: true, placeholder: '192.168.0.10' },
  { key: 'mac', label: 'MAC address', kind: 'mac', card: true, placeholder: 'AA:BB:CC:DD:EE:FF' },
  { key: 'patch', label: 'Patch panel', kind: 'patch', card: true, placeholder: 'R1 PP8 T05' },
  { key: 'note', label: 'Note', kind: 'textarea', card: false },
];

export const ENDPOINT_FIELDS = [
  { key: 'setor', label: 'Setor' },
  { key: 'referencia', label: 'Referência' },
  { key: 'baia', label: 'Baia' },
  { key: 'letra', label: 'Letra' },
  { key: 'jack', label: 'Endpoint' },
  { key: 'cabling', label: 'Status infra cabeada' },
];

const PATCH_RE = /^\s*R\s*(\d+)\s*PP\s*(\d+)\s*T\s*(\d+)\s*$/i;

export function parsePatch(text) {
  const m = PATCH_RE.exec(String(text ?? ''));
  if (!m) return null;
  return { rack: `R${Number(m[1])}`, panel: Number(m[2]), port: Number(m[3]) };
}

export function formatPatch(p) {
  return `${p.rack} ${cellKey(p.panel, p.port)}`;
}

export function cellKey(panel, port) {
  return `PP${panel} T${String(port).padStart(2, '0')}`;
}

export function isValidIPv4(text) {
  const parts = String(text).split('.');
  return parts.length === 4 && parts.every((p) => /^\d{1,3}$/.test(p) && Number(p) <= 255);
}

export function normalizeMac(text) {
  const hex = String(text).replace(/[^0-9a-f]/gi, '');
  if (hex.length !== 12) return null;
  return hex.toUpperCase().match(/../g).join(':');
}

// Returns { value } with the normalized value, or { error } for invalid input.
// An empty string is always valid and clears the field.
export function normalizeField(kind, raw) {
  const text = String(raw ?? '').trim();
  if (!text) return { value: '' };
  switch (kind) {
    case 'ip':
      return isValidIPv4(text) ? { value: text } : { error: 'Expected an IPv4 address like 192.168.0.10' };
    case 'mac': {
      const mac = normalizeMac(text);
      return mac ? { value: mac } : { error: 'Expected 12 hex digits, e.g. AA:BB:CC:DD:EE:FF' };
    }
    case 'patch': {
      const p = parsePatch(text);
      return p ? { value: formatPatch(p) } : { error: 'Expected rack, panel and port, e.g. R1 PP8 T05' };
    }
    default:
      return { value: text };
  }
}

export function stateMap(doc) {
  return new Map(doc.states.map((s) => [s.id, s]));
}

export function stateOf(doc, id) {
  return stateMap(doc).get(id) ?? { id, label: id || 'Unknown', color: '#6b7280', pattern: 'solid' };
}

export function findDevice(doc, id) {
  return doc.devices.find((d) => d.id === id) ?? null;
}

export function findRack(doc, id) {
  return doc.racks.find((r) => r.id === id) ?? null;
}

export function getPort(device, n) {
  return { state: DEFAULT_STATE, ...(device.port_data?.[String(n)] ?? {}) };
}

function isEmptyPort(port) {
  return Object.entries(port).every(([k, v]) =>
    (k === 'state' && v === DEFAULT_STATE) || v === '' || v === false || v == null);
}

// Ports with only default values are removed so the data file stays small.
export function setPort(device, n, port) {
  device.port_data ??= {};
  const clean = Object.fromEntries(Object.entries(port).filter(([, v]) => v !== '' && v != null && v !== false));
  if (isEmptyPort({ state: DEFAULT_STATE, ...clean })) delete device.port_data[String(n)];
  else device.port_data[String(n)] = { state: DEFAULT_STATE, ...clean };
}

export function getCell(rack, panel, port) {
  return { state: DEFAULT_STATE, ...(rack.cells?.[cellKey(panel, port)] ?? {}) };
}

export function setCell(rack, panel, port, cell) {
  rack.cells ??= {};
  const clean = Object.fromEntries(Object.entries(cell).filter(([, v]) => v !== '' && v != null));
  const key = cellKey(panel, port);
  if (Object.keys(clean).every((k) => k === 'state') && (clean.state ?? DEFAULT_STATE) === DEFAULT_STATE) delete rack.cells[key];
  else rack.cells[key] = { state: DEFAULT_STATE, ...clean };
}

export function endpointsAt(doc, patch) {
  return (doc.endpoints ?? []).filter((e) => e.patch === patch);
}

// Every device port whose patch field points at this patch-panel position.
export function portsUsingPatch(doc, patch) {
  const out = [];
  for (const d of doc.devices) {
    for (const [n, p] of Object.entries(d.port_data ?? {})) {
      if (p.patch === patch) out.push({ device: d.id, port: Number(n) });
    }
  }
  return out;
}

// Path from a device port outwards: linked device port, patch-panel cell, desk endpoints.
export function chainFor(doc, deviceId, n) {
  const device = findDevice(doc, deviceId);
  const port = getPort(device, n);
  const result = { port, link: null, patch: null, rack: null, cell: null, endpoints: [] };
  if (port.link) {
    const other = findDevice(doc, port.link.device);
    if (other) result.link = { device: other, port: port.link.port };
  }
  const p = parsePatch(port.patch);
  if (p) {
    result.patch = formatPatch(p);
    result.rack = findRack(doc, p.rack);
    if (result.rack && p.panel <= result.rack.panels && p.port <= result.rack.ports_per_panel) {
      result.cell = getCell(result.rack, p.panel, p.port);
    }
    result.endpoints = endpointsAt(doc, result.patch);
  }
  return result;
}

// Links are stored on both ends. Linking a port first unlinks whatever either end was linked to.
export function setLink(doc, a, b) {
  const unlink = (ref) => {
    const dev = findDevice(doc, ref.device);
    if (!dev) return;
    const port = getPort(dev, ref.port);
    if (port.link) {
      const peer = findDevice(doc, port.link.device);
      if (peer) {
        const peerPort = getPort(peer, port.link.port);
        if (peerPort.link?.device === ref.device && peerPort.link?.port === ref.port) {
          delete peerPort.link;
          setPort(peer, port.link.port, peerPort);
        }
      }
      delete port.link;
      setPort(dev, ref.port, port);
    }
  };
  unlink(a);
  if (!b) return;
  unlink(b);
  const devA = findDevice(doc, a.device);
  const devB = findDevice(doc, b.device);
  setPort(devA, a.port, { ...getPort(devA, a.port), link: { device: b.device, port: b.port } });
  setPort(devB, b.port, { ...getPort(devB, b.port), link: { device: a.device, port: a.port } });
}

// IPs and MACs used by more than one port, as Map(value -> [{device, port}]).
export function findDuplicates(doc) {
  const seen = { ip: new Map(), mac: new Map() };
  for (const d of doc.devices) {
    for (const [n, p] of Object.entries(d.port_data ?? {})) {
      for (const key of ['ip', 'mac']) {
        if (!p[key]) continue;
        const list = seen[key].get(p[key]) ?? [];
        list.push({ device: d.id, port: Number(n) });
        seen[key].set(p[key], list);
      }
    }
  }
  for (const key of ['ip', 'mac']) {
    for (const [v, list] of seen[key]) if (list.length < 2) seen[key].delete(v);
  }
  return seen;
}

export function countStates(device) {
  const counts = {};
  for (let n = 1; n <= device.ports; n++) {
    const s = getPort(device, n).state;
    counts[s] = (counts[s] ?? 0) + 1;
  }
  return counts;
}

export function portMatches(doc, device, n, query) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const port = getPort(device, n);
  const chain = chainFor(doc, device.id, n);
  const hay = [
    String(n), port.name, port.connected, port.ip, port.mac, port.patch, port.note,
    stateOf(doc, port.state).label,
    ...chain.endpoints.flatMap((e) => ENDPOINT_FIELDS.map((f) => e[f.key])),
  ];
  return hay.some((v) => v != null && String(v).toLowerCase().includes(q));
}

export function slugId(name, taken) {
  const base = String(name).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'device';
  let id = base;
  for (let i = 2; taken.has(id); i++) id = `${base}-${i}`;
  return id;
}

// Ports above `count` that still hold data; resizing a device would drop them.
export function portsAbove(device, count) {
  return Object.keys(device.port_data ?? {}).map(Number).filter((n) => n > count).sort((a, b) => a - b);
}

export function removeDevice(doc, id) {
  for (const d of doc.devices) {
    for (const [n, p] of Object.entries(d.port_data ?? {})) {
      if (p.link?.device === id) {
        delete p.link;
        setPort(d, Number(n), p);
      }
    }
  }
  doc.devices = doc.devices.filter((d) => d.id !== id);
}
