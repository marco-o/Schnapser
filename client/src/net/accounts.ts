// The accounts this device remembers, and who plays in this tab.
//
// Logging in or registering gives the device a key (server: db.py). The
// browser keeps every account logged in on it (localStorage, so a shared
// tablet can hold several), and each tab keeps who confirmed they are
// playing there (sessionStorage): opening the site again only asks "who's
// playing?", never the password. A tab may also play as a guest (unrated).
//
// No DOM or React here: the functions take the storage, so `node --test`
// runs them with a stand-in (accounts.test.ts).

export interface Account {
  readonly username: string;
  readonly key: string;
}

/** The part of Storage used here. */
export interface KeyValue {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export const ACCOUNTS_KEY = 'schnaps.accounts';
export const PLAYER_KEY = 'schnaps.player';
/** The PLAYER_KEY value of a tab that plays as a guest (no username has
 *  a "+": server db.clean_username). */
const GUEST = '+guest';

function read(store: KeyValue, key: string): string | null {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

function write(store: KeyValue, key: string, value: string | null): void {
  try {
    if (value === null) store.removeItem(key);
    else store.setItem(key, value);
  } catch {
    // Storage unavailable: it lasts as long as the page.
  }
}

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

/** The accounts remembered on this device, most recently used first. */
export function loadAccounts(store: KeyValue): Account[] {
  const raw = read(store, ACCOUNTS_KEY);
  if (raw === null) return [];
  try {
    const list: unknown = JSON.parse(raw);
    if (!Array.isArray(list)) return [];
    return list.filter(
      (a): a is Account =>
        a !== null &&
        typeof a === 'object' &&
        typeof (a as Account).username === 'string' &&
        typeof (a as Account).key === 'string',
    );
  } catch {
    return [];
  }
}

/** Remembers an account (replacing an older key for the same username). */
export function rememberAccount(store: KeyValue, account: Account): Account[] {
  const list = [account, ...loadAccounts(store).filter(a => !same(a.username, account.username))];
  write(store, ACCOUNTS_KEY, JSON.stringify(list));
  return list;
}

/** Forgets an account on this device. */
export function forgetAccount(store: KeyValue, username: string): Account[] {
  const list = loadAccounts(store).filter(a => !same(a.username, username));
  write(store, ACCOUNTS_KEY, JSON.stringify(list));
  return list;
}

/**
 * Who plays in this tab: an account, null for a guest, or undefined when
 * nobody has confirmed yet (or the account is no longer remembered).
 */
export function currentPlayer(
  session: KeyValue,
  accounts: readonly Account[],
): Account | null | undefined {
  const who = read(session, PLAYER_KEY);
  if (who === null) return undefined;
  if (who === GUEST) return null;
  return accounts.find(a => same(a.username, who));
}

/** Confirms who plays in this tab (null: a guest; undefined: ask again). */
export function setCurrentPlayer(session: KeyValue, who: Account | null | undefined): void {
  write(session, PLAYER_KEY, who === undefined ? null : who === null ? GUEST : who.username);
}
