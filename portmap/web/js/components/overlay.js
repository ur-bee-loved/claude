import { h, clear, icon, ICONS } from '../dom.js';

// Side drawer, modal dialog and toast notifications. Each uses one element in
// index.html (#drawer, #dialog, #toasts).

const drawer = () => document.getElementById('drawer');
let drawerOnClose = null;

// onSubmit runs on Ctrl/Cmd+Enter inside the drawer.
export function openDrawer({ kicker, title, accent, body, footer, onClose, onSubmit }) {
  const el = drawer();
  drawerOnClose = onClose ?? null;
  el.onkeydown = onSubmit ? (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) onSubmit(); } : null;
  clear(el).append(
    h('header', { class: 'drawer-head', style: accent ? { '--accent': accent } : null },
      h('div', {},
        kicker && h('div', { class: 'kicker' }, kicker),
        h('h2', { class: 'drawer-title' }, title)),
      h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close', onclick: closeDrawer }, icon(ICONS.close))),
    h('div', { class: 'drawer-body' }, body),
    footer && h('footer', { class: 'drawer-foot' }, footer),
  );
  el.classList.add('open');
  el.setAttribute('aria-hidden', 'false');
  el.querySelector('input, select, textarea, button:not(.icon-btn)')?.focus({ preventScroll: true });
}

export function closeDrawer() {
  const el = drawer();
  if (!el.classList.contains('open')) return;
  el.classList.remove('open');
  el.setAttribute('aria-hidden', 'true');
  const fn = drawerOnClose;
  drawerOnClose = null;
  fn?.();
}

export function isDrawerOpen() {
  return drawer().classList.contains('open');
}

// actions: [{ label, kind: 'primary' | 'danger' | 'ghost', onClick }]. Returning
// false from onClick keeps the dialog open (e.g. after a validation error).
// `target` is the <dialog> id; confirmations use their own so they can open
// on top of a form dialog.
export function openDialog({ title, body, actions, target = 'dialog' }) {
  const dlg = document.getElementById(target);
  const close = () => dlg.close();
  const buttons = actions.map((a) => h('button', {
    type: 'button',
    class: `btn ${a.kind ?? 'ghost'}`,
    onclick: async () => {
      if ((await a.onClick?.()) !== false) close();
    },
  }, a.label));
  clear(dlg).append(
    h('form', { method: 'dialog', class: 'dialog-card', onsubmit: (e) => { e.preventDefault(); buttons.at(-1).click(); } },
      h('h2', { class: 'dialog-title' }, title),
      h('div', { class: 'dialog-body' }, body),
      h('div', { class: 'dialog-actions' }, buttons)),
  );
  dlg.showModal();
  dlg.querySelector('input, select')?.focus();
  return close;
}

export function confirmDialog(title, message, { danger = false, confirmLabel = 'Confirm' } = {}) {
  return new Promise((resolve) => {
    const dlg = document.getElementById('confirm');
    let answered = false;
    dlg.addEventListener('close', () => { if (!answered) resolve(false); }, { once: true });
    openDialog({
      target: 'confirm',
      title,
      body: h('p', {}, message),
      actions: [
        { label: 'Cancel', onClick: () => { answered = true; resolve(false); } },
        { label: confirmLabel, kind: danger ? 'danger' : 'primary', onClick: () => { answered = true; resolve(true); } },
      ],
    });
  });
}

export function toast(message, { kind = 'info', action, timeout = 4000 } = {}) {
  const box = document.getElementById('toasts');
  const el = h('div', { class: `toast ${kind}`, role: 'status' },
    h('span', {}, message),
    action && h('button', { type: 'button', class: 'btn ghost small', onclick: () => { action.onClick(); el.remove(); } }, action.label));
  box.append(el);
  if (timeout) setTimeout(() => el.remove(), timeout);
}
