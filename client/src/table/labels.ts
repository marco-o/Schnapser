// Names shown for seats, pairs and phases, in the table's language
// (i18n/strings.ts). Seats are named by who sits there, never by a compass
// point.

import {botLabel, contractName, type Lang, t} from '../i18n/strings.ts';
import type {Phase, SeatInfo} from '../net/api.ts';

/** Table seats 0..3, clockwise; seats 0 and 2 are partners, so are 1 and 3. */
export const SEAT_NUMBERS = [0, 1, 2, 3] as const;

/** A seat's name: who sits there, or "Seat N" while it is empty. */
export function seatName(lang: Lang, seats: readonly SeatInfo[], seat: number): string {
  const s = seats[seat];
  if (!s || s.kind === 'empty') return t(lang, 'seatN', {n: seat + 1});
  return s.name;
}

/** A pair by its players: "Anna & Hermione". */
export function pairNames(lang: Lang, pair: number, seats: readonly SeatInfo[]): string {
  return t(lang, 'pairOf', {a: seatName(lang, seats, pair), b: seatName(lang, seats, pair + 2)});
}

/** A seat in a chooser: "Seat 1 (partner of seat 3)". */
export function seatChoice(lang: Lang, seat: number): string {
  return t(lang, 'seatChoice', {n: seat + 1, m: ((seat + 2) % 4) + 1});
}

export function phaseLabel(lang: Lang, phase: Phase): string {
  switch (phase) {
    case 'open':
      return t(lang, 'phaseOpen');
    case 'playing':
      return t(lang, 'phasePlaying');
    case 'deal_over':
      return t(lang, 'phaseDealOver');
    case 'match_over':
      return t(lang, 'phaseMatchOver');
    case 'closed':
      return t(lang, 'phaseClosed');
  }
}

/** A rating change with its sign: "+16", "−9", "±0". */
export function signed(n: number): string {
  if (n > 0) return `+${n}`;
  if (n < 0) return `−${-n}`;
  return '±0';
}

/** A pair by its rating identities' names: "Anna & Bologna bot". */
export function standingName(
  lang: Lang,
  players: ReadonlyArray<{readonly name: string; readonly bot: boolean}>,
): string {
  const [a, b] = players.map(p =>
    p.bot ? t(lang, 'botNamed', {label: botLabel(lang, p.name)}) : p.name,
  );
  return t(lang, 'pairOf', {a: a ?? '', b: b ?? ''});
}

/** Why a set was not rated (server: table.UNRATED_*), in `lang`. */
export function unratedText(lang: Lang, reason: string | null): string {
  switch (reason) {
    case 'seats changed':
      return t(lang, 'unratedSeats');
    case 'same pair':
      return t(lang, 'unratedSamePair');
    default:
      return t(lang, 'unratedGuest');
  }
}

/** A contract with its flecks: "Lomt ×4". */
export function contractText(lang: Lang, name: string, flecks: number): string {
  const shown = contractName(lang, name);
  return flecks > 0 ? `${shown} ×${2 ** flecks}` : shown;
}
