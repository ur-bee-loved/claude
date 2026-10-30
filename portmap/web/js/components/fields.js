import { h } from '../dom.js';

// Labeled form controls with an inline error line. Each returns
// { el, input, setError(msg) } so callers can validate before saving.

let uid = 0;

function wrap(label, input, hint) {
  const id = `f${++uid}`;
  input.id = id;
  const err = h('div', { class: 'field-error', 'aria-live': 'polite' });
  const el = h('div', { class: 'field' },
    h('label', { for: id }, label),
    input,
    hint && h('div', { class: 'field-hint' }, hint),
    err);
  return {
    el,
    input,
    setError(msg) {
      err.textContent = msg ?? '';
      el.classList.toggle('invalid', Boolean(msg));
    },
  };
}

export function textField({ label, value = '', placeholder, hint, multiline, suggestions, mono, type = 'text', min, max }) {
  let list = null;
  if (suggestions?.length) {
    list = h('datalist', { id: `dl${++uid}` }, suggestions.map((s) => h('option', { value: s })));
  }
  const input = multiline
    ? h('textarea', { rows: 3, placeholder, value })
    : h('input', { type, placeholder, value: String(value), autocomplete: 'off', spellcheck: 'false', min, max });
  if (mono) input.classList.add('mono');
  if (list) input.setAttribute('list', list.id);
  const f = wrap(label, input, hint);
  if (list) f.el.append(list);
  return f;
}

export function selectField({ label, value, options, hint }) {
  const input = h('select', {},
    options.map((o) => h('option', { value: o.value, selected: o.value === value }, o.label)));
  return wrap(label, input, hint);
}

export function checkField({ label, checked }) {
  const input = h('input', { type: 'checkbox', checked: Boolean(checked) });
  const el = h('label', { class: 'check' }, input, h('span', {}, label));
  return { el, input, setError() {} };
}
