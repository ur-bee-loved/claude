import { h } from '../dom.js';

// State legend that doubles as a filter: clicking a chip hides or shows that state.
export function legend(doc, hiddenStates, onToggle) {
  return h('div', { class: 'legend', role: 'group', 'aria-label': 'Port states' },
    doc.states.map((s) => h('button', {
      type: 'button',
      class: `chip${hiddenStates.has(s.id) ? ' off' : ''}`,
      'aria-pressed': String(!hiddenStates.has(s.id)),
      style: { '--state': s.color },
      dataset: { pattern: s.pattern ?? 'solid' },
      onclick: () => onToggle(s.id),
    }, h('span', { class: 'swatch' }), s.label)));
}

// Thin bar with one segment per state, sized by how many ports are in it.
export function stateBar(doc, counts, total) {
  return h('div', { class: 'state-bar', role: 'img', 'aria-label': doc.states.filter((s) => counts[s.id]).map((s) => `${counts[s.id]} ${s.label}`).join(', ') },
    doc.states.filter((s) => counts[s.id]).map((s) => h('span', {
      title: `${s.label}: ${counts[s.id]}`,
      style: { '--state': s.color, flex: String(counts[s.id] / total) },
    })));
}
