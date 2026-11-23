// The site's REST API (server/schnaps_web/app.py) and the browser-kept seat
// tokens and nickname.

import type {Frame, Presentation} from '../gui/table_types.ts';
import type {Lang} from '../i18n/strings.ts';
import {
  type Account,
  currentPlayer,
  forgetAccount as forget,
  type KeyValue,
  loadAccounts,
  rememberAccount as remember,
  setCurrentPlayer,
} from './accounts.ts';

export type {Account} from './accounts.ts';

export interface SeatInfo {
  readonly kind: 'empty' | 'human' | 'bot';
  readonly name: string;
  readonly bot: string | null;
  /** The bot's kind as the site offers it ("Bologna", "Firenze", "Verona", "Napoli"). */
  readonly botLabel?: string | null;
  readonly online: boolean;
  readonly you: boolean;
  /** A logged-in user (rated), not a guest. */
  readonly account?: boolean;
}

/** Each pair's rating (seats 0+2, 1+3); null while a seat is a guest or empty. */
export type PairRatings = readonly [number | null, number | null];

/** The rating line of a set that just ended (server: Table._rate_set). */
export interface SetRating {
  readonly rated: boolean;
  /** Why not rated: "guest", "seats changed", "same pair"; null when rated. */
  readonly unrated: string | null;
  readonly before: readonly number[] | null;
  readonly after: readonly number[] | null;
}

/** One rated pair (GET /api/ratings, best first). */
export interface PairStanding {
  readonly key: string;
  readonly players: ReadonlyArray<{readonly name: string; readonly bot: boolean}>;
  readonly rating: number;
  readonly won: number;
  readonly lost: number;
  readonly last: string | null;
}

export interface TableSummary {
  readonly id: string;
  readonly name: string;
  /** The language the table shows, chosen when it was started. */
  readonly lang: Lang;
  readonly phase: Phase;
  readonly seats: readonly SeatInfo[];
  readonly need: readonly number[] | null;
  readonly sets: readonly number[] | null;
  readonly ratings?: PairRatings;
}

export type Phase = 'open' | 'playing' | 'deal_over' | 'match_over' | 'closed';

export interface DealResult {
  readonly number: number;
  readonly set_number: number;
  readonly dealer: number;
  readonly caller: number;
  readonly contract: string;
  readonly declarer: number | null;
  readonly flecks: number;
  readonly winner: number;
  readonly points: number;
  readonly need_after: readonly number[];
  /** The cardthrowup that ended the deal (docs/cardthrowup.md), or null. */
  readonly throw?: DealThrow | null;
}

/** A recorded throw: who (table seat) and which. */
export interface DealThrow {
  readonly kind: ThrowKind;
  readonly seat: number;
  readonly text: string;
}

export type ThrowKind = 'resign';

/** The throw in a frame's view (game seats; deal.Throw.to_json). */
export interface FrameThrow {
  readonly kind: ThrowKind;
  /** The thrower's game seat. */
  readonly seat: number;
  readonly trick: number;
  readonly text: string;
}

export interface MatchInfo {
  readonly dealer: number;
  readonly caller: number;
  readonly need: readonly number[];
  readonly sets: readonly number[];
  readonly setNumber: number;
  readonly winner: number | null;
  readonly deals: readonly DealResult[];
}

export interface TableFrame extends Frame {
  readonly seatMap: readonly number[];
  readonly presentation: Presentation;
  /** What the viewer may do now: resign, show the hand (none to spectators). */
  readonly throws?: {readonly resign: boolean; readonly show: boolean};
}

/** What the table's WebSocket pushes (table.snapshot on the server). */
export interface TableSnapshot {
  readonly type: 'table';
  readonly id: string;
  readonly name: string;
  /** The language the table shows, chosen when it was started. */
  readonly lang: Lang;
  readonly phase: Phase;
  readonly you: number | null;
  readonly isCreator: boolean;
  readonly seats: readonly SeatInfo[];
  readonly match: MatchInfo | null;
  readonly ratings?: PairRatings;
  readonly dealer: number | null;
  readonly toMove: number | null;
  readonly frame: TableFrame | null;
  /** Every hand is shown: the all-cards watch port. */
  readonly reveal?: boolean;
  readonly lastResult: {
    readonly deal: DealResult;
    readonly setWinner: number | null;
    readonly matchWinner: number | null;
    /** When a set just ended: its rating change, or why it was not rated. */
    readonly rating?: SetRating | null;
  } | null;
  readonly bots: ReadonlyArray<{readonly name: string; readonly label: string}>;
  /** Between deals: the table seats holding the next deal back ("Wait"). */
  readonly waiting?: readonly number[];
}

const TOKEN_KEY = (tableId: string) => `schnaps.token.${tableId}`;
const NAME_KEY = 'schnaps.nickname';

function load(key: string, store: Storage = localStorage): string | null {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

function save(key: string, value: string | null, store: Storage = localStorage): void {
  try {
    if (value === null) store.removeItem(key);
    else store.setItem(key, value);
  } catch {
    // Storage unavailable: the seat lasts as long as the page.
  }
}

// A seat token is kept per tab (sessionStorage: a reload keeps this tab's
// seat, even with two players in one browser) and per browser (localStorage:
// a new tab or a restarted browser finds the seat again).
export const tokenOf = (tableId: string) =>
  load(TOKEN_KEY(tableId), sessionStorage) ?? load(TOKEN_KEY(tableId));
export const setToken = (tableId: string, token: string | null) => {
  save(TOKEN_KEY(tableId), token, sessionStorage);
  save(TOKEN_KEY(tableId), token);
};
export const nickname = () => load(NAME_KEY) ?? '';
export const setNickname = (name: string) => save(NAME_KEY, name);

// The accounts on this device and who plays in this tab (accounts.ts).
const local = (): KeyValue => {
  try {
    return localStorage;
  } catch {
    return NO_STORAGE;
  }
};
const session = (): KeyValue => {
  try {
    return sessionStorage;
  } catch {
    return NO_STORAGE;
  }
};
const NO_STORAGE: KeyValue = {getItem: () => null, setItem: () => {}, removeItem: () => {}};
export const accounts = () => loadAccounts(local());
export const rememberAccount = (a: Account) => remember(local(), a);
export const forgetAccount = (username: string) => forget(local(), username);
/** Who plays in this tab: an account, null (a guest), undefined (ask). */
export const player = () => currentPlayer(session(), accounts());
export const setPlayer = (who: Account | null | undefined) => setCurrentPlayer(session(), who);

export class ApiError extends Error {
  /** The HTTP status (401: the device key is unknown; log in again). */
  readonly status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.status = status;
  }
}

async function call<T>(
  method: string,
  path: string,
  body?: unknown,
  token?: string | null,
  userKey?: string | null,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers['X-Seat-Token'] = token;
  if (userKey) headers['X-User-Key'] = userKey;
  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? null : JSON.stringify(body),
  });
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      data !== null && typeof data === 'object' && 'detail' in data
        ? String((data as {detail: unknown}).detail)
        : response.statusText;
    throw new ApiError(detail, response.status);
  }
  return data as T;
}

/** Who sits down: a guest's nickname, or an account (by its key). */
export type Sitter = {readonly nickname: string} | {readonly account: Account};

const sitter = (who: Sitter) =>
  'account' in who
    ? {body: {}, key: who.account.key}
    : {body: {player: who.nickname}, key: null};

export const api = {
  /** Which app serves the page: the watch port is read-only, all cards shown. */
  site: () => call<{watch: boolean}>('GET', '/api/site'),
  tables: () => call<TableSummary[]>('GET', '/api/tables'),
  ratings: () => call<PairStanding[]>('GET', '/api/ratings'),
  register: (username: string, password: string) =>
    call<Account>('POST', '/api/accounts', {username, password}),
  login: (username: string, password: string) =>
    call<Account>('POST', '/api/login', {username, password}),
  /** Checks a device key (ApiError 401 when the server no longer knows it). */
  me: (key: string) => call<{username: string}>('GET', '/api/me', undefined, null, key),
  logout: (key: string) => call('POST', '/api/logout', {}, null, key),
  create: (name: string, who: Sitter, seat: number, lang: Lang) => {
    const s = sitter(who);
    return call<{id: string; token: string}>(
      'POST',
      '/api/tables',
      {...s.body, name, seat, lang},
      null,
      s.key,
    );
  },
  sit: (id: string, seat: number, who: Sitter) => {
    const s = sitter(who);
    return call<{token: string}>('POST', `/api/tables/${id}/seats/${seat}`, s.body, null, s.key);
  },
  setBot: (id: string, seat: number, bot: string, token: string | null) =>
    call('PUT', `/api/tables/${id}/seats/${seat}/bot`, {bot}, token),
  emptySeat: (id: string, seat: number, token: string | null) =>
    call('DELETE', `/api/tables/${id}/seats/${seat}`, undefined, token),
  start: (id: string, token: string | null) =>
    call('POST', `/api/tables/${id}/start`, {}, token),
  act: (id: string, action: number, token: string | null) =>
    call('POST', `/api/tables/${id}/actions`, {action}, token),
  /** Resign (docs/cardthrowup.md). */
  throwCards: (id: string, kind: ThrowKind, token: string | null) =>
    call('POST', `/api/tables/${id}/throw`, {kind}, token),
  /** Show the hand to the two opponents (docs/cardthrowup.md). */
  show: (id: string, token: string | null) =>
    call('POST', `/api/tables/${id}/show`, {}, token),
  /** Between deals: hold the next deal back (on) or let it come (off). */
  wait: (id: string, on: boolean, token: string | null) =>
    call('POST', `/api/tables/${id}/wait`, {on}, token),
  close: (id: string, token: string | null) =>
    call('DELETE', `/api/tables/${id}`, undefined, token),
};
