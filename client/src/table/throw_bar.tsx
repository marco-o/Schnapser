// cardthrowup (docs/cardthrowup.md): the bar under the player's hand with
// Show (the hand open to the two opponents, so they can see the deal is
// lost and resign) and Resign, and the notices: who has shown their cards,
// who resigned.
//
// Show keeps the deal going; Resign ends it. Each asks to confirm, as
// neither can be undone.

import {type JSX, useEffect, useState} from 'react';

import {useLang, useT} from '../i18n/lang.tsx';
import {type Key} from '../i18n/strings.ts';
import {api, type DealThrow, type FrameThrow, type TableSnapshot} from '../net/api.ts';
import {seatName} from './labels.ts';

type Asking = 'show' | 'resign';

/** Show and Resign for the seated player, with a confirm step. */
export function ThrowBar({
  snapshot,
  tableId,
  token,
  run,
}: {
  readonly snapshot: TableSnapshot;
  readonly tableId: string;
  readonly token: string | null;
  readonly run: (job: () => Promise<unknown>) => void;
}): JSX.Element | null {
  const tr = useT();
  const [asking, setAsking] = useState<Asking | null>(null);
  const offered = snapshot.frame?.throws;
  const dealNumber = snapshot.match?.deals.length ?? 0;
  // A new deal (or the offer going away) drops a pending question.
  useEffect(() => {
    setAsking(null);
  }, [dealNumber]);
  if (snapshot.phase !== 'playing' || !offered || !(offered.resign || offered.show)) {
    return null;
  }
  if (asking !== null && offered[asking]) {
    const question: Key = asking === 'resign' ? 'throwResignConfirm' : 'throwShowConfirm';
    return (
      <div className="site-felt__actions site-throw" role="group" aria-label={tr('throwBar')}>
        <span className="site-throw__question">{tr(question)}</span>
        <button
          type="button"
          className="button site-throw__yes"
          onClick={() => {
            setAsking(null);
            run(() =>
              asking === 'resign'
                ? api.throwCards(tableId, 'resign', token)
                : api.show(tableId, token),
            );
          }}
        >
          {tr('throwYes')}
        </button>
        <button type="button" className="button" onClick={() => setAsking(null)}>
          {tr('throwCancel')}
        </button>
      </div>
    );
  }
  return (
    <div className="site-felt__actions site-throw" role="group" aria-label={tr('throwBar')}>
      {offered.show && (
        <button type="button" className="button" onClick={() => setAsking('show')}>
          {tr('throwShow')}
        </button>
      )}
      {offered.resign && (
        <button type="button" className="button" onClick={() => setAsking('resign')}>
          {tr('throwResign')}
        </button>
      )}
    </div>
  );
}

/** Who resigned (the deal is over), or who has shown their cards. */
export function ThrowNotice({snapshot}: {readonly snapshot: TableSnapshot}): JSX.Element | null {
  const lang = useLang();
  const tr = useT();
  const frame = snapshot.frame;
  // The view is the renderer's (game/view.py present); "throw" and "shown"
  // are ours.
  const view = frame?.presentation.view as
    | {throw?: FrameThrow | null; shown?: readonly number[]}
    | undefined;
  if (!frame || !view) return null;
  // The frame names game seats; seatMap turns them into table seats.
  const name = (gameSeat: number) =>
    seatName(lang, snapshot.seats, frame.seatMap[gameSeat] ?? gameSeat);
  const thrown = view.throw;
  if (thrown) {
    return (
      <div className="site-throw-notice" role="status" data-kind={thrown.kind}>
        <strong>{tr('throwResigns', {name: name(thrown.seat)})}</strong>
      </div>
    );
  }
  const shown = view.shown ?? [];
  if (snapshot.phase !== 'playing' || shown.length === 0) return null;
  return (
    <div className="site-throw-notice" role="status" data-kind="show">
      {shown.map(seat => (
        <span key={seat}>{tr('throwShows', {name: name(seat)})}</span>
      ))}
    </div>
  );
}

/** A throw as the score sheet marks it: "resigned". */
export function throwMark(tr: (key: Key) => string, thrown: DealThrow | null | undefined): string {
  return thrown ? tr('sheetResigned') : '';
}
