// Rating labels (labels.ts) and the account errors (i18n/strings.ts).

import assert from 'node:assert/strict';
import {test} from 'node:test';

import {serverError} from '../i18n/strings.ts';
import {signed, standingName, unratedText} from './labels.ts';

test('rating changes carry their sign', () => {
  assert.equal(signed(16), '+16');
  assert.equal(signed(-9), '−9');
  assert.equal(signed(0), '±0');
});

test('rated pairs name their bots by kind, in the language', () => {
  const players = [
    {name: 'Bologna', bot: true},
    {name: 'Anna', bot: false},
  ];
  assert.equal(standingName('en', players), 'Bologna bot & Anna');
  assert.equal(standingName('de', players), 'Bologna-Bot & Anna');
  assert.equal(standingName('it', [{name: 'Firenze', bot: true}, {name: 'Ben', bot: false}]), 'bot Firenze & Ben');
});

test('why a set is not rated', () => {
  assert.match(unratedText('en', 'guest'), /not every player is logged in/);
  assert.match(unratedText('en', 'seats changed'), /players changed/);
  assert.match(unratedText('de', 'same pair'), /dasselbe Paar/);
});

test('account errors from the server are translated', () => {
  assert.equal(serverError('it', 'wrong username or password'), 'Nome utente o password errati');
  assert.equal(
    serverError('de', 'the password needs at least 4 characters'),
    'Das Passwort braucht mindestens 4 Zeichen',
  );
  assert.equal(serverError('en', 'a username may not contain +'), 'a username may not contain +');
  assert.equal(
    serverError('it', 'that name belongs to an account; log in to use it'),
    'Questo nome appartiene a un account; accedi per usarlo',
  );
});
