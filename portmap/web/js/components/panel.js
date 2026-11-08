import { h, icon, ICONS } from '../dom.js';
import { setExpanded } from '../store.js';

// A device or rack panel that folds into its header. The body is built only
// while the panel is open. `open` overrides the saved choice (used while a
// search is active, so panels with matches open by themselves). `handle` is an
// optional element drawn before the title, such as a drag handle.
export function collapsiblePanel({ key, open, iconPath, title, sub, bar, actions, body, handle, className = '' }) {
  const bodyId = `panel-${key.replace(/[^a-z0-9-]/gi, '-')}`;
  return h('section', { class: `device-panel ${className}${open ? '' : ' collapsed'}`, 'aria-label': title },
    h('header', { class: 'device-head' },
      handle,
      h('button', {
        type: 'button',
        class: 'panel-toggle',
        'aria-expanded': String(open),
        'aria-controls': bodyId,
        title: open ? 'Collapse' : 'Expand',
        onclick: () => setExpanded([key], !open),
      },
      h('span', { class: 'chevron' }, icon(ICONS.chevron, 18)),
      h('span', { class: 'device-icon' }, icon(iconPath, 22)),
      h('span', { class: 'device-titles' },
        h('span', { class: 'device-name' }, title),
        h('span', { class: 'device-sub' }, sub))),
      h('div', { class: 'device-actions' }, actions)),
    bar,
    open && h('div', { class: 'panel-body', id: bodyId }, body()));
}

// "Expand all / Collapse all" pair for a view's toolbar.
export function foldAllButtons(keys) {
  return h('div', { class: 'fold-all' },
    h('button', { type: 'button', class: 'btn ghost small', onclick: () => setExpanded(keys, true) }, icon(ICONS.expand, 14), 'Expand all'),
    h('button', { type: 'button', class: 'btn ghost small', onclick: () => setExpanded(keys, false) }, icon(ICONS.collapse, 14), 'Collapse all'));
}
