import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  CABLING_STATUSES, DEFAULT_STATE, cablingOf, chainFor, countStates, deskAt, findDuplicates, getCell, getPort,
  moveDevice, normalizeField, normalizeMac, parsePatch, portMatches, portsAbove, portsUsingPatch, removeDevice,
  setCell, setDesk, setLink, setPort, shiftDevice, slugId,
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
  setPort(d, 2, { state: DEFAULT_STATE, name: '', collective: false });
  assert.deepEqual(d.port_data, {});
  setPort(d, 2, { state: DEFAULT_STATE, name: 'A' });
  assert.deepEqual(d.port_data, { 2: { state: DEFAULT_STATE, name: 'A' } });
  assert.equal(getPort(d, 3).state, DEFAULT_STATE);
});

test('setCell drops default-only cells', () => {
  const r = { id: 'R1', panels: 1, ports_per_panel: 4, cells: {} };
  setCell(r, 1, 2, { state: 'damaged', note: '' });
  assert.deepEqual(r.cells, { 'PP1 T02': { state: 'damaged' } });
  setCell(r, 1, 2, { state: DEFAULT_STATE, note: '' });
  assert.deepEqual(r.cells, {});
  assert.equal(getCell(r, 1, 2).state, DEFAULT_STATE);
});

test('chainFor follows link, patch cell and desk', () => {
  const doc = example();
  const c = chainFor(doc, 'core', 4);
  assert.equal(c.patch, 'R1 PP2 T01');
  assert.equal(c.cell.state, 'available');
  assert.equal(c.desk.referencia, 'Mesa 1');
  assert.equal(chainFor(doc, 'core', 9).desk, null);
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
  assert.ok(portMatches(doc, core, 4, 'íntegra'));
  assert.ok(portMatches(doc, core, 6, 'parcialmente'));
  assert.ok(portMatches(doc, core, 3, '00:00:20'));
  assert.ok(!portMatches(doc, core, 4, 'printer'));
  assert.equal(countStates(core)[DEFAULT_STATE], 17);
  assert.deepEqual(portsUsingPatch(doc, 'R1 PP1 T10'), [{ device: 'core', port: 8 }]);
  assert.deepEqual(portsAbove(core, 8), [9, 12]);
  assert.equal(slugId('Switch Ação', new Set(['switch-acao'])), 'switch-acao-2');
});

test('setDesk keeps one record per position and drops empty ones', () => {
  const doc = { desks: {} };
  setDesk(doc, 'R1 PP1 T01', { setor: 'Op', referencia: 'Mesa 4', baia: '', letra: 'A', cabling: 'ok' });
  assert.deepEqual(deskAt(doc, 'R1 PP1 T01'), { setor: 'Op', referencia: 'Mesa 4', letra: 'A', cabling: 'ok' });
  setDesk(doc, 'R1 PP1 T01', { setor: '', referencia: 'Mesa 5', cabling: 'unidentified' });
  assert.deepEqual(Object.keys(doc.desks), ['R1 PP1 T01']);
  assert.deepEqual(doc.desks['R1 PP1 T01'], { referencia: 'Mesa 5' });
  setDesk(doc, 'R1 PP1 T01', { setor: '', referencia: '', cabling: 'unidentified' });
  assert.deepEqual(doc.desks, {});
  assert.equal(deskAt(doc, 'R1 PP1 T01'), null);
});

test('cabling statuses: the five options, empty means not identified', () => {
  assert.deepEqual(CABLING_STATUSES.map((c) => c.label),
    ['Íntegra', 'Parcialmente danificada', 'Sem soquete', 'Não instalada', 'Não identificada']);
  assert.equal(cablingOf('').label, 'Não identificada');
  assert.equal(cablingOf(undefined).id, 'unidentified');
  assert.equal(cablingOf('novo').label, 'novo');
});

test('moveDevice and shiftDevice reorder the list', () => {
  const ids = (doc) => doc.devices.map((d) => d.id).join('');
  const make = () => ({ devices: ['a', 'b', 'c', 'd'].map((id) => ({ id })) });
  let doc = make();
  assert.equal(moveDevice(doc, 'a', 'c', true), true);
  assert.equal(ids(doc), 'bcad');
  doc = make();
  assert.equal(moveDevice(doc, 'd', 'b', false), true);
  assert.equal(ids(doc), 'adbc');
  doc = make();
  assert.equal(moveDevice(doc, 'a', 'b', false), false);
  assert.equal(moveDevice(doc, 'b', 'a', true), false);
  assert.equal(moveDevice(doc, 'a', 'a', true), false);
  assert.equal(moveDevice(doc, 'a', 'zz', true), false);
  assert.equal(ids(doc), 'abcd');
  assert.equal(shiftDevice(doc, 'b', -1), true);
  assert.equal(ids(doc), 'bacd');
  assert.equal(shiftDevice(doc, 'b', -1), false);
  assert.equal(shiftDevice(doc, 'd', 1), false);
  assert.equal(ids(doc), 'bacd');
});
