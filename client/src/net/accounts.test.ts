// The remembered accounts and who plays in a tab (accounts.ts).

import assert from 'node:assert/strict';
import {test} from 'node:test';

import {
  ACCOUNTS_KEY,
  currentPlayer,
  forgetAccount,
  type KeyValue,
  loadAccounts,
  rememberAccount,
  setCurrentPlayer,
} from './accounts.ts';

function store(): KeyValue & {readonly data: Map<string, string>} {
  const data = new Map<string, string>();
  return {
    data,
    getItem: k => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: k => void data.delete(k),
  };
}

test('a device remembers several accounts, the latest first', () => {
  const local = store();
  assert.deepEqual(loadAccounts(local), []);
  rememberAccount(local, {username: 'Anna', key: 'k1'});
  rememberAccount(local, {username: 'Ben', key: 'k2'});
  // Logging in again replaces the older key, whatever the case.
  const list = rememberAccount(local, {username: 'anna', key: 'k3'});
  assert.deepEqual(list, [
    {username: 'anna', key: 'k3'},
    {username: 'Ben', key: 'k2'},
  ]);
  assert.deepEqual(loadAccounts(local), list);
  assert.deepEqual(forgetAccount(local, 'BEN'), [{username: 'anna', key: 'k3'}]);
});

test('broken or foreign storage reads as no accounts', () => {
  const local = store();
  local.setItem(ACCOUNTS_KEY, 'not json');
  assert.deepEqual(loadAccounts(local), []);
  local.setItem(ACCOUNTS_KEY, JSON.stringify([{username: 'A'}, {username: 'B', key: 'k'}, 3]));
  assert.deepEqual(loadAccounts(local), [{username: 'B', key: 'k'}]);
  const broken: KeyValue = {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {
      throw new Error('blocked');
    },
    removeItem: () => {},
  };
  assert.deepEqual(loadAccounts(broken), []);
  assert.deepEqual(rememberAccount(broken, {username: 'A', key: 'k'}), [{username: 'A', key: 'k'}]);
});

test('each tab confirms who plays: an account, a guest, or not yet', () => {
  const session = store();
  const accounts = [{username: 'Anna', key: 'k1'}];
  assert.equal(currentPlayer(session, accounts), undefined);
  setCurrentPlayer(session, accounts[0]);
  assert.deepEqual(currentPlayer(session, accounts), accounts[0]);
  // An account forgotten on the device asks again.
  assert.equal(currentPlayer(session, []), undefined);
  setCurrentPlayer(session, null);
  assert.equal(currentPlayer(session, accounts), null);
  setCurrentPlayer(session, undefined);
  assert.equal(currentPlayer(session, accounts), undefined);
});
