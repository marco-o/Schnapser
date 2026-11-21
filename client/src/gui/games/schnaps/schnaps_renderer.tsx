// Copyright 2026 DeepMind Technologies Limited
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// The schnaps renderer: a four-seat table laid out as a bridge table, the
// bottom seat's partner across, play running clockwise (bottom, left, top,
// right), the trick in the middle and the contract and score in a corner.
//
// Copied for schnaps-web from the OpenSpiel GUI
// (gui/src/games/schnaps/schnaps_renderer.tsx). Changes: it takes its props
// directly instead of the GUI's renderer registry, draws the viewer's seat
// at the bottom (spectators: `bottomSeat`), and names seats by
// `seatLabels` (nicknames) instead of "Player N".

import type {JSX} from 'react';

import type {Suit} from '../../cards/card.ts';
import {CardFace} from '../../cards/card_face.tsx';
import {cardActions} from '../../cards/card_hints.ts';
import {Hand} from '../../cards/hand.tsx';
import {readHints} from '../../renderers/hints.ts';
import {
  field,
  number,
  optionalField,
  record,
  string,
} from '../../renderers/struct_reader.ts';
import type {Frame, Presentation} from '../../table_types.ts';
import {
  SCHNAPS_SKIN,
  type SchnapsDeclaration,
  type SchnapsPlay,
  type SchnapsView,
  readSchnapsView,
  suitName,
} from './schnaps_view.ts';

import './schnaps.css';

/** Where a seat sits, relative to the seat drawn at the bottom. */
type Place = 'bottom' | 'left' | 'top' | 'right';

const PLACES: readonly Place[] = ['bottom', 'left', 'top', 'right'];

function placeOf(seat: number, bottom: number): Place {
  return PLACES[(seat - bottom + 4) % 4] ?? 'bottom';
}

/** The props of the table. */
export interface SchnapsTableProps {
  /** The frame, as the server built it for the viewer. */
  readonly frame: Frame;
  /** The frame's presentation: the view and the viewer's hinted moves. */
  readonly presentation: Presentation;
  /** Plays an action id; null when the viewer cannot move. */
  readonly play: ((action: number) => void) | null;
  /** The name of each game seat (0..3); default "Player N". */
  readonly seatLabels?: readonly string[];
  /** The game seat drawn at the bottom when the viewer has none. */
  readonly bottomSeat?: number;
}

// The seat names of the table being drawn (set at the top of each render).
let labels: readonly string[] = [];

function seatName(seat: number): string {
  return labels[seat] ?? `Player ${String(seat)}`;
}

function teamName(team: number): string {
  return `${seatName(team)} + ${seatName(team + 2)}`;
}

function statusText(view: SchnapsView, frame: Frame): string {
  const mover = view.toMove === null ? '' : seatName(view.toMove);
  switch (view.phase) {
    case 'deal':
      return 'Dealing…';
    case 'trump':
      return `${mover} chooses trump from the first three cards`;
    case 'bidding':
      return `Bidding: ${mover} calls, flecks or passes`;
    case 'play':
      return `${mover} to play`;
    case 'terminal': {
      const returns = frame.returns ?? [];
      const value = returns[0] ?? 0;
      const winner = value >= 0 ? 0 : 1;
      return `${teamName(winner)} win ${String(Math.abs(value))} points`;
    }
    default: {
      const unreachable: never = view.phase;
      throw new Error(`Unhandled phase: ${String(unreachable)}`);
    }
  }
}

/** The trump, the contract and each team's points and tricks. */
function InfoBox({view}: {readonly view: SchnapsView}): JSX.Element {
  const {trump, contract} = view;
  return (
    <dl className="schnaps-info" aria-label="Deal">
      <div className="schnaps-info__item">
        <dt>Trump</dt>
        <dd>
          {trump === null ? (
            '—'
          ) : (
            <>
              <SuitIcon suit={trump} /> {suitName(trump)}
            </>
          )}
        </dd>
      </div>
      <div className="schnaps-info__item">
        <dt>Contract</dt>
        <dd>
          {contract === null
            ? '—'
            : `${contract.name} (${seatName(contract.declarer)})`}
          {contract !== null && contract.flecks > 0
            ? ` ×${String(2 ** contract.flecks)}`
            : ''}
        </dd>
      </div>
      {[0, 1].map(team => (
        <div className="schnaps-info__item" key={team}>
          <dt>{teamName(team)}</dt>
          <dd>
            {`${String(view.score[team] ?? 0)} pts · ${String(view.tricks[team] ?? 0)} tricks`}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** A 20 or 40 as the table names it: "40 ♥ Herz". */
function declarationText(d: SchnapsDeclaration): string {
  return `${String(d.points)} ${suitName(d.suit)}`;
}

// schnaps-web: the suits are drawn with the deck's own suit signs
// (client/public/suits, cut by scripts/cut_suits.py), not French glyphs.
const TRUMP_SUITS: readonly Suit[] = ['h', 'd', 's', 'c']; // actions 28..31

/** The suit a trump-choice action names, or null for any other action. */
function trumpOfAction(action: number): Suit | null {
  return action >= 28 && action < 32 ? (TRUMP_SUITS[action - 28] ?? null) : null;
}

/** A suit's sign as a picture, named for screen readers. */
function SuitIcon({suit}: {readonly suit: Suit}): JSX.Element {
  return (
    <img
      className="schnaps-suit"
      src={`/suits/${suit}.png`}
      alt={suitName(suit)}
      draggable={false}
    />
  );
}

/** The trick in play, or the last one, each card before its player. */
function TrickArea({
  view,
  bottom,
}: {
  readonly view: SchnapsView;
  readonly bottom: number;
}): JSX.Element {
  const last = view.trick.length === 0 ? view.lastTrick : null;
  const showingLast = last !== null;
  // The 20 or 40 that led the trick shown, announced on the felt.
  const done = (view.tricks[0] ?? 0) + (view.tricks[1] ?? 0);
  const shownTrick = showingLast ? done - 1 : done;
  const announced = view.declarations.find(d => d.trick === shownTrick);
  const plays: readonly SchnapsPlay[] = last === null ? view.trick : last.cards;
  const caption =
    last === null ? 'Trick' : `Last trick: ${seatName(last.winner)} won`;
  return (
    <section
      className="schnaps-trick"
      aria-label={caption}
      data-last={showingLast ? 'true' : undefined}
    >
      {plays.map(play => (
        <div
          className="schnaps-trick__card"
          data-place={placeOf(play.seat, bottom)}
          key={play.seat}
        >
          <CardFace code={play.card} skin={SCHNAPS_SKIN} />
        </div>
      ))}
      {announced !== undefined && (
        <p className="schnaps-announce" role="status">
          {`${seatName(announced.seat)}: ${String(announced.points)} `}
          <SuitIcon suit={announced.suit} />
          {` ${suitName(announced.suit)}`}
        </p>
      )}
      <p className="schnaps-trick__caption">{caption}</p>
    </section>
  );
}

/** One seat's hand at its place, marked while it is that seat's turn. */
function SeatArea({
  view,
  seat,
  bottom,
  playable,
  play,
}: {
  readonly view: SchnapsView;
  readonly seat: number;
  readonly bottom: number;
  readonly playable: ReadonlyMap<string, number>;
  readonly play: ((action: number) => void) | null;
}): JSX.Element {
  const entry = view.seats[seat];
  // schnaps-web: the Caller (game seat 0) shows the trump's sign; every
  // seat shows its bids (Pass, Fleck, a contract) next to its name.
  const trump = seat === 0 ? view.trump : null;
  const bids = view.bids
    .filter(b => b.seat === seat)
    .map(b => b.bid)
    .join(', ');
  const said = view.declarations
    .filter(d => d.seat === seat)
    .map(declarationText)
    .join(', ');
  const label = [
    seatName(seat),
    trump === null ? '' : `trump ${suitName(trump)}`,
    bids,
    said,
  ]
    .filter(Boolean)
    .join(' · ');
  const title = (
    <>
      {seatName(seat)}
      {trump !== null && (
        <>
          {' '}
          <SuitIcon suit={trump} />
        </>
      )}
      {bids && <span className="schnaps-bids"> {bids}</span>}
      {said && ` · ${said}`}
    </>
  );
  return (
    <div
      className="schnaps-seat"
      data-place={placeOf(seat, bottom)}
      data-active={view.toMove === seat ? 'true' : undefined}
    >
      <Hand
        label={label}
        title={title}
        cards={entry?.cards ?? []}
        playable={playable}
        play={play}
        skin={SCHNAPS_SKIN}
        fanned={seat !== bottom}
      />
    </div>
  );
}

/** schnaps-web: a call's chance of success is shown above this. */
const CHANCE_SHOWN = 0.2;

/** The buttons for every action that is not a card: calls, declarations. */
function MoveButtons({
  presentation,
  play,
}: Pick<SchnapsTableProps, 'presentation' | 'play'>): JSX.Element | null {
  const buttons = readHints(presentation, (hint, path) => {
    if (hint === null) return null;
    const fields = record(hint, path);
    // schnaps-web: a call may carry its chance of success ("chance").
    const chance = optionalField(hint, path, 'chance', number, null);
    if ('button' in fields) {
      return {text: field(hint, path, 'button', string), chance};
    }
    if ('declare' in fields) {
      return {text: field(hint, path, 'label', string), chance};
    }
    return null;
  });
  if (buttons.length === 0) return null;
  return (
    <div className="schnaps-moves" role="group" aria-label="Moves">
      {buttons.map(({action, hint: {text: name, chance}}) => {
        // schnaps-web: a call's chance of success shows when above 20%.
        const text =
          chance !== null && chance > CHANCE_SHOWN
            ? `${name} ${String(Math.round(chance * 100))}%`
            : name;
        // schnaps-web: a trump choice shows the suit's picture, not its name.
        const trump = trumpOfAction(action);
        return (
          <button
            type="button"
            className={trump === null ? 'button' : 'button button--suit'}
            key={action}
            disabled={play === null}
            aria-label={text}
            title={text}
            onClick={() => {
              play?.(action);
            }}
          >
            {trump === null ? text : <SuitIcon suit={trump} />}
          </button>
        );
      })}
    </div>
  );
}

/** Draws a schnaps frame as a bridge-style card table. */
export function SchnapsRenderer({
  frame,
  presentation,
  play,
  seatLabels = [],
  bottomSeat = 0,
}: SchnapsTableProps): JSX.Element {
  labels = seatLabels;
  const view = readSchnapsView(presentation.view);
  const bottom = frame.viewer.seat ?? bottomSeat;
  const playable = cardActions(presentation);
  return (
    <div className="schnaps">
      <p className="schnaps-status" role="status">
        {statusText(view, frame)}
      </p>
      <div className="schnaps-table">
        <InfoBox view={view} />
        {[0, 1, 2, 3].map(seat => (
          <SeatArea
            key={seat}
            view={view}
            seat={seat}
            bottom={bottom}
            playable={playable}
            play={play}
          />
        ))}
        <TrickArea view={view} bottom={bottom} />
      </div>
      <MoveButtons presentation={presentation} play={play} />
    </div>
  );
}
