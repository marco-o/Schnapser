// The translation table: complete, consistent, and the user's game terms.
// Run: npm test (node --test; scripts/test.sh runs it too).

import assert from 'node:assert/strict';
import {test} from 'node:test';

import {
  actionText,
  asLang,
  bidText,
  cardName,
  contractName,
  DEFAULT_LANG,
  type Key,
  LANGS,
  rankIndex,
  serverError,
  STRINGS,
  suitName,
  t,
} from './strings.ts';

const params = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort();

test('every string has every language, with the same parameters', () => {
  for (const [key, entry] of Object.entries(STRINGS)) {
    for (const lang of LANGS) {
      assert.ok(entry[lang].length > 0, `${key} has no ${lang}`);
      assert.deepEqual(params(entry[lang]), params(entry.en), `${key}: ${lang} parameters`);
    }
  }
});

test('Italian is preselected; anything unknown falls back to it', () => {
  assert.equal(DEFAULT_LANG, 'it');
  assert.equal(asLang('de'), 'de');
  assert.equal(asLang('fr'), 'it');
  assert.equal(asLang(null), 'it');
});

test('t fills parameters and keeps unknown ones', () => {
  assert.equal(t('en', 'seatN', {n: 3}), 'Seat 3');
  assert.equal(t('de', 'seatN', {n: 3}), 'Platz 3');
  assert.equal(t('it', 'seatN', {n: 3}), 'Posto 3');
  assert.equal(t('it', 'seatN'), 'Posto {n}');
});

test('Italian ranks are the user\'s; suits stay German everywhere', () => {
  assert.equal(cardName('it', 'A', 'h'), 'Asso di Herz');
  assert.equal(cardName('it', 'T', 'd'), 'Dieci di Caro');
  assert.equal(cardName('it', 'K', 's'), 'Re di Pik');
  assert.equal(cardName('it', 'Q', 'c'), 'Cavallo di Kreuz');
  assert.equal(cardName('it', 'J', 'h'), 'Nižek di Herz');
  assert.equal(cardName('de', 'K', 'h'), 'Herz König');
  assert.equal(cardName('en', 'J', 'c'), 'Kreuz Unter');
  for (const lang of LANGS) {
    assert.deepEqual(
      (['h', 'd', 's', 'c'] as const).map(s => suitName(lang, s)),
      ['Herz', 'Caro', 'Pik', 'Kreuz'],
    );
  }
  assert.deepEqual(
    (['J', 'Q', 'K', 'T', 'A'] as const).map(r => rankIndex('it', r)),
    ['N', 'C', 'R', '10', 'A'],
  );
});

test('Pass is Weiter in German and Via in Italian; the rest stays German', () => {
  assert.equal(bidText('en', 'Pass'), 'Pass');
  assert.equal(bidText('de', 'Pass'), 'Weiter');
  assert.equal(bidText('it', 'Pass'), 'Via');
  for (const lang of LANGS) {
    assert.equal(bidText(lang, 'Fleck'), 'Fleck');
    for (const c of ['Normal', 'Schnapser', 'Lomt', 'Bauern', 'Jodler', 'Hermort']) {
      assert.equal(contractName(lang, c), c);
      assert.equal(bidText(lang, c), c);
    }
  }
});

test('move buttons are built from the action id', () => {
  assert.equal(actionText('it', 32, 'Pass', null, 'h'), 'Via');
  assert.equal(actionText('de', 33, 'Fleck', null, 'h'), 'Fleck');
  assert.equal(actionText('it', 35, 'Lomt', null, 'h'), 'Lomt');
  assert.equal(actionText('it', 28, 'Trump: Herz', null, null), 'Briscola: Herz');
  assert.equal(actionText('de', 31, 'Trump: Kreuz', null, null), 'Trumpf: Kreuz');
  // A 40 in trump, a 20 outside it.
  assert.equal(
    actionText('it', 20, 'Declare 40, lead Herz König', {rank: 'K', suit: 'h'}, 'h'),
    'Accusa 40, gioca Re di Herz',
  );
  assert.equal(
    actionText('de', 23, 'Declare 20, lead Caro Ober', {rank: 'Q', suit: 'd'}, 'h'),
    '20 ansagen, Caro Ober ausspielen',
  );
  // Unknown actions keep the server's text.
  assert.equal(actionText('it', 99, 'Something new', null, null), 'Something new');
});

test('server errors are translated; seats count from 1', () => {
  assert.equal(serverError('de', 'seat 2 is taken'), 'Platz 3 ist besetzt');
  assert.equal(serverError('en', 'seat 0 is taken'), 'seat 1 is taken');
  assert.equal(serverError('it', 'every seat must be filled first'), 'Prima vanno occupati tutti i posti');
  assert.equal(
    serverError('it', 'the nickname is longer than 20 characters'),
    'Il soprannome supera 20 caratteri',
  );
  assert.equal(
    serverError('de', "only the table's creator may do that"),
    'Das darf nur, wer den Tisch eröffnet hat',
  );
  assert.equal(serverError('it', 'something unexpected'), 'something unexpected');
});

test('every error key is a server message pattern', () => {
  const errors = (Object.keys(STRINGS) as Key[]).filter(k => k.startsWith('err'));
  assert.ok(errors.length > 10);
  for (const key of errors) {
    const sample = STRINGS[key].en.replace(/\{\w+\}/g, '7');
    assert.notEqual(serverError('it', sample), sample, key);
  }
});
