import { h, icon, ICONS } from '../dom.js';
import { DEFAULT_CABLING, cablingOf } from '../model.js';

// "Status infra cabeada" as a tag. An empty or unidentified status is flagged
// with a warning mark, so a desk nobody has checked stands out.
export function cablingTag(status) {
  const c = cablingOf(status);
  const flagged = c.id === DEFAULT_CABLING;
  return h('span', {
    class: `tag${flagged ? ' flagged' : ''}`,
    style: { '--state': c.color },
    title: flagged ? 'Cabling status not identified' : `Status infra cabeada: ${c.label}`,
  }, flagged && icon(ICONS.warn, 11), c.label);
}
