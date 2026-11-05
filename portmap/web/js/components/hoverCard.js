import { h } from '../dom.js';

// One floating card shared by every hoverable element. It opens on mouse hover
// and on keyboard focus, sits above the element (below when there is no room)
// and never takes pointer events, so clicks still reach the element under it.

const GAP = 10;
const MARGIN = 8;
let card = null;
let owner = null;

function element() {
  if (!card) {
    card = h('div', { class: 'hovercard', role: 'tooltip', id: 'hovercard', 'aria-hidden': 'true' });
    document.body.append(card);
    window.addEventListener('scroll', follow, { capture: true, passive: true });
    window.addEventListener('resize', follow);
  }
  return card;
}

// build() returns { accent, content } and runs each time the card opens, so
// it always shows current data.
export function hoverable(el, build) {
  el.addEventListener('pointerenter', (e) => {
    if (e.pointerType !== 'touch') show(el, build);
  });
  el.addEventListener('pointerleave', hide);
  el.addEventListener('focus', () => show(el, build));
  el.addEventListener('blur', hide);
  el.addEventListener('click', hide);
  el.setAttribute('aria-describedby', 'hovercard');
}

function show(el, build) {
  const c = element();
  const { accent, content } = build();
  owner = el;
  c.style.setProperty('--accent', accent);
  c.replaceChildren(content);
  c.classList.add('measuring');
  place(el);
  c.classList.remove('measuring');
  c.classList.add('open');
  c.setAttribute('aria-hidden', 'false');
}

// Keeps the card next to its element while the page scrolls or resizes.
function follow() {
  if (!owner) return;
  if (owner.isConnected) place(owner);
  else hide();
}

function place(el) {
  const c = card;
  const box = c.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const topbar = document.querySelector('.topbar')?.getBoundingClientRect().bottom ?? 0;
  let top = r.top - box.height - GAP;
  let side = 'above';
  if (top < Math.max(topbar, 0) + MARGIN) {
    top = r.bottom + GAP;
    side = 'below';
  }
  const left = Math.min(Math.max(r.left + r.width / 2 - box.width / 2, MARGIN), window.innerWidth - box.width - MARGIN);
  c.style.top = `${Math.round(top)}px`;
  c.style.left = `${Math.round(left)}px`;
  c.style.setProperty('--arrow-x', `${Math.round(r.left + r.width / 2 - left)}px`);
  c.dataset.side = side;
}

export function hide() {
  if (!card || !owner) return;
  owner = null;
  card.classList.remove('open');
  card.setAttribute('aria-hidden', 'true');
}
