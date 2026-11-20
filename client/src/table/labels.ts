// Names shown for seats, pairs and phases.

import type {Phase, SeatInfo} from '../net/api.ts';

/** Table seats 0..3, clockwise. */
export const SEAT_NAMES = ['South', 'West', 'North', 'East'] as const;

/** Pair 0 is South + North (seats 0, 2), pair 1 West + East (seats 1, 3). */
export function pairLabel(pair: number): string {
  return pair === 0 ? 'South–North' : 'West–East';
}

/** A seat's name; bots also say where they sit ("Large (West)"). */
export function seatName(seats: readonly SeatInfo[], seat: number): string {
  const s = seats[seat];
  const where = SEAT_NAMES[seat] ?? `Seat ${String(seat)}`;
  if (!s || s.kind === 'empty') return where;
  return s.kind === 'bot' ? `${s.name} (${where})` : s.name;
}

export function pairNames(pair: number, seats: readonly SeatInfo[]): string {
  return `${seatName(seats, pair)} & ${seatName(seats, pair + 2)}`;
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
