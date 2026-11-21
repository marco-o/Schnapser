// Names shown for seats, pairs and phases. Seats are named by who sits
// there, never by a compass point.

import type {Phase, SeatInfo} from '../net/api.ts';

/** Table seats 0..3, clockwise; seats 0 and 2 are partners, so are 1 and 3. */
export const SEAT_NUMBERS = [0, 1, 2, 3] as const;

/** A seat's name: who sits there, or "Seat N" while it is empty. */
export function seatName(seats: readonly SeatInfo[], seat: number): string {
  const s = seats[seat];
  if (!s || s.kind === 'empty') return `Seat ${String(seat + 1)}`;
  return s.name;
}

/** A pair by its players: "Anna & Hermione". */
export function pairNames(pair: number, seats: readonly SeatInfo[]): string {
  return `${seatName(seats, pair)} & ${seatName(seats, pair + 2)}`;
}

/** A seat in a chooser: "Seat 1 (partner of seat 3)". */
export function seatChoice(seat: number): string {
  return `Seat ${String(seat + 1)} (partner of seat ${String(((seat + 2) % 4) + 1)})`;
}

export function phaseLabel(phase: Phase): string {
  switch (phase) {
    case 'open':
      return 'Waiting for players';
    case 'playing':
      return 'Playing';
    case 'deal_over':
      return 'Deal over';
    case 'match_over':
      return 'Match over';
    case 'closed':
      return 'Closed';
  }
}

export function contractText(name: string, flecks: number): string {
  return flecks > 0 ? `${name} ×${2 ** flecks}` : name;
}
