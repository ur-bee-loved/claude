import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  chainFor, countStates, findDuplicates, getPort, normalizeField, normalizeMac, parsePatch, portMatches,
  portsAbove, portsUsingPatch, removeDevice, setCell, setLink, setPort, slugId, getCell,
} from '../js/model.js';

const example = () => JSON.parse(readFileSync(new URL('../../data/network.example.json', import.meta.url), 'utf8'));
const dev = (doc, id) => doc.devices.find((d) => d.id === id);

test('parsePatch accepts loose spacing and case', () => {
  assert.deepEqual(parsePatch(' r1 pp8 t5 '), { rack: 'R1', panel: 8, port: 5 });
  assert.equal(parsePatch('R1 PP8'), null);
});

test('normalizeField validates and normalizes', () => {
  assert.deepEqual(normalizeField('ip', '10.0.0.255'), { value: '10.0.0.255' });
  assert.ok(normalizeField('ip', '10.0.0.256').error);
  assert.ok(normalizeField('ip', '10.0.0').error);
  assert.deepEqual(normalizeField('mac', 'aa-bb-cc-dd-ee-0f'), { value: 'AA:BB:CC:DD:EE:0F' });
  assert.equal(normalizeMac('aabbccddee'), null);
  assert.deepEqual(normalizeField('patch', 'r2pp12t8'), { value: 'R2 PP12 T08' });
  assert.deepEqual(normalizeField('mac', '  '), { value: '' });
});

test('setPort drops default-only ports', () => {
  const d = { id: 'x', ports: 4, port_data: {} };
  setPort(d, 2, { state: 'available', name: '', critical: false });
  assert.deepEqual(d.port_data, {});
  setPort(d, 2, { state: 'available', name: 'A' });
  assert.deepEqual(d.port_data, { 2: { state: 'available', name: 'A' } });
  assert.equal(getPort(d, 3).state, 'available');
});

test('setCell drops default-only cells', () => {
  const r = { id: 'R1', panels: 1, ports_per_panel: 4, cells: {} };
  setCell(r, 1, 2, { state: 'damaged', note: '' });
  assert.deepEqual(r.cells, { 'PP1 T02': { state: 'damaged' } });
  setCell(r, 1, 2, { state: 'available', note: '' });
  assert.deepEqual(r.cells, {});
  assert.equal(getCell(r, 1, 2).state, 'available');
});

test('chainFor follows link, patch cell and desks', () => {
  const doc = example();
  const c = chainFor(doc, 'core', 4);
  assert.equal(c.patch, 'R1 PP2 T01');
  assert.equal(c.cell.state, 'full_chain');
  assert.equal(c.endpoints[0].referencia, 'Mesa 1');
  const l = chainFor(doc, 'core', 1);
  assert.equal(l.link.device.id, 'router');
  assert.equal(l.link.port, 2);
});

test('setLink keeps both ends consistent', () => {
  const doc = example();
  setLink(doc, { device: 'core', port: 2 }, { device: 'router', port: 2 });
  assert.deepEqual(getPort(dev(doc, 'core'), 2).link, { device: 'router', port: 2 });
  assert.deepEqual(getPort(dev(doc, 'router'), 2).link, { device: 'core', port: 2 });
  assert.equal(getPort(dev(doc, 'core'), 1).link, undefined);
  setLink(doc, { device: 'router', port: 2 }, null);
  assert.equal(getPort(dev(doc, 'core'), 2).link, undefined);
  assert.equal(dev(doc, 'core').port_data['2'], undefined);
});

test('removeDevice clears links pointing at it', () => {
  const doc = example();
  removeDevice(doc, 'router');
  assert.equal(dev(doc, 'router'), undefined);
  assert.equal(getPort(dev(doc, 'core'), 1).link, undefined);
});

test('findDuplicates reports shared IPs and MACs only', () => {
  const doc = example();
  assert.equal(findDuplicates(doc).ip.size, 0);
  setPort(dev(doc, 'core'), 5, { ...getPort(dev(doc, 'core'), 5), ip: '192.0.2.20' });
  assert.deepEqual(findDuplicates(doc).ip.get('192.0.2.20'), [{ device: 'core', port: 3 }, { device: 'core', port: 5 }]);
});

test('search, counts and helpers', () => {
  const doc = example();
  const core = dev(doc, 'core');
  assert.ok(portMatches(doc, core, 4, 'sales'));
  assert.ok(portMatches(doc, core, 3, '00:00:20'));
  assert.ok(!portMatches(doc, core, 4, 'printer'));
  assert.equal(countStates(core).available, 16);
  assert.deepEqual(portsUsingPatch(doc, 'R1 PP1 T10'), [{ device: 'core', port: 8 }]);
  assert.deepEqual(portsAbove(core, 8), [9, 12]);
  assert.equal(slugId('Switch Ação', new Set(['switch-acao'])), 'switch-acao-2');
});
