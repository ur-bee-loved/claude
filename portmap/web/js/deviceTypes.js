// Kinds of network equipment the tool can draw. To support a new kind, add an
// entry here; it then shows up in the "Add device" dialog.
//
// layout: 'odd-even' draws odd ports on the top row and even ports below, like
//         most rack switches; 'row' draws a single row.
// icon:   SVG path data on a 24x24 grid, drawn as a stroke.

export const DEVICE_TYPES = {
  switch: {
    label: 'Switch',
    defaultPorts: 24,
    layout: 'odd-even',
    icon: 'M3 7h18v10H3z M6 11h2v2H6z M10 11h2v2h-2z M14 11h2v2h-2z',
  },
  router: {
    label: 'Router',
    defaultPorts: 5,
    layout: 'row',
    icon: 'M3 13h18v6H3z M7 16h.01 M11 16h.01 M8 13l-2-6 M16 13l2-6',
  },
  firewall: {
    label: 'Firewall',
    defaultPorts: 8,
    layout: 'row',
    icon: 'M3 5h18v14H3z M3 10h18 M3 14h18 M9 5v5 M15 10v4 M9 14v5',
  },
  access_point: {
    label: 'Access point',
    defaultPorts: 1,
    layout: 'row',
    icon: 'M12 18h.01 M8.5 14.5a5 5 0 0 1 7 0 M5.5 11.5a9 9 0 0 1 13 0',
  },
  other: {
    label: 'Other',
    defaultPorts: 8,
    layout: 'row',
    icon: 'M4 6h16v12H4z M8 10h8 M8 14h5',
  },
};

export function deviceType(id) {
  return DEVICE_TYPES[id] ?? DEVICE_TYPES.other;
}

// Suggestions offered in the "Connected device" field.
export const CONNECTED_KINDS = [
  'Access point', 'Printer', 'Switch', 'Router', 'Gateway', 'Workstation',
  'Server', 'Room outlet', 'Camera', 'IP phone', 'Raspberry Pi',
];
