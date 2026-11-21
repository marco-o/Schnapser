// cardthrowup (docs/cardthrowup.md): the bar under the player's hand with
// Resign and Allmine ("my side takes every remaining trick"), and the
// notice of a throw once the deal ends.
//
// Allmine shows during the whole card play, whether or not the claim
// holds: showing it only when valid would tell the player they have a
// forced win. The server checks it with every hand open; a wrong claim
// counts as resigning. Both throws end the deal, so each asks to confirm.

import {type JSX, useEffect, useState} from 'react';

import {parseCard} from '../gui/cards/card.ts';
import {useLang, useT} from '../i18n/lang.tsx';
import {cardName, type Key} from '../i18n/strings.ts';
import {
  api,
  type DealThrow,
  type FrameThrow,
  type TableSnapshot,
  type ThrowKind,
} from '../net/api.ts';
import {seatName} from './labels.ts';

/** Resign and Allmine for the seated player, with a confirm step. */
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
  const [asking, setAsking] = useState<ThrowKind | null>(null);
  const offered = snapshot.frame?.throws;
  const dealNumber = snapshot.match?.deals.length ?? 0;
  // A new deal (or the offer going away) drops a pending question.
  useEffect(() => {
    setAsking(null);
  }, [dealNumber]);
  if (snapshot.phase !== 'playing' || !offered || !(offered.resign || offered.allmine)) {
    return null;
  }
  if (asking !== null && offered[asking]) {
    const question: Key = asking === 'resign' ? 'throwResignConfirm' : 'throwAllmineConfirm';
    return (
      <div className="site-felt__actions site-throw" role="group" aria-label={tr('throwBar')}>
        <span className="site-throw__question">{tr(question)}</span>
        <button
          type="button"
          className="button site-throw__yes"
          onClick={() => {
            setAsking(null);
            run(() => api.throwCards(tableId, asking, token));
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
      {offered.allmine && (
        <button type="button" className="button" onClick={() => setAsking('allmine')}>
          {tr('throwAllmine')}
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

/** What happened when a deal ended by a throw: who, which, the verdict. */
export function ThrowNotice({snapshot}: {readonly snapshot: TableSnapshot}): JSX.Element | null {
  const lang = useLang();
  const tr = useT();
  const frame = snapshot.frame;
  // The view is the renderer's (game/view.py present); "throw" is ours.
  const view = frame?.presentation.view as {throw?: FrameThrow | null} | undefined;
  const thrown = view?.throw;
  if (!frame || !thrown) return null;
  // The frame names game seats; seatMap turns them into table seats.
  const name = (gameSeat: number) =>
    seatName(lang, snapshot.seats, frame.seatMap[gameSeat] ?? gameSeat);
  const who = name(thrown.seat);
  let verdict = '';
  if (thrown.kind === 'allmine') {
    const reason = thrown.reason;
    if (thrown.accepted) {
      verdict = tr('throwChecked');
    } else if (reason?.seat !== undefined && reason.card) {
      const card = parseCard(reason.card);
      verdict = tr('throwRefusedBy', {
        name: name(reason.seat),
        card: cardName(lang, card.rank, card.suit),
      });
    } else {
      verdict = tr('throwRefused');
    }
  }
  return (
    <div className="site-throw-notice" role="status" data-kind={thrown.kind}>
      <strong>
        {tr(thrown.kind === 'resign' ? 'throwResigns' : 'throwClaims', {name: who})}
      </strong>
      {verdict && (
        <span data-accepted={thrown.accepted ? 'true' : 'false'}>{verdict}</span>
      )}
    </div>
  );
}

/** A throw as the score sheet marks it: "resigned", "allmine", … */
export function throwMark(tr: (key: Key) => string, thrown: DealThrow | null | undefined): string {
  if (!thrown) return '';
  if (thrown.kind === 'resign') return tr('sheetResigned');
  return tr(thrown.accepted ? 'sheetAllmine' : 'sheetAllmineRefused');
}
