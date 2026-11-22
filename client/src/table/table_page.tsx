// One table: the scoreboard, the seats (with the creator's bot controls),
// the card table (the copied OpenSpiel schnaps renderer), the result of the
// last deal and the score sheet. Everything shows in the table's language
// (snapshot.lang, chosen when the table was started; i18n/strings.ts).

import {type JSX, useEffect, useState} from 'react';

import {SchnapsRenderer} from '../gui/games/schnaps/schnaps_renderer.tsx';
import {LangContext, storedLang, useLang, useT} from '../i18n/lang.tsx';
import {botLabel, type Key, type Lang, type Params, serverError, t} from '../i18n/strings.ts';
import {
  api,
  ApiError,
  forgetAccount,
  nickname,
  player,
  setNickname,
  setPlayer,
  type SetRating,
  setToken,
  type TableSnapshot,
  tokenOf,
} from '../net/api.ts';
import {useTable} from '../net/use_table.ts';
import {
  contractText,
  pairNames,
  phaseLabel,
  seatName,
  signed,
  unratedText,
} from './labels.ts';
import {ThrowBar, throwMark, ThrowNotice} from './throw_bar.tsx';

export function TablePage({
  tableId,
  go,
  watch,
}: {
  readonly tableId: string;
  readonly go: (path: string) => void;
  /** The all-cards watch port: read-only, no seat token. */
  readonly watch: boolean;
}): JSX.Element {
  const [token, setLocalToken] = useState(watch ? null : tokenOf(tableId));
  const {snapshot, connection} = useTable(tableId, token);
  const [error, setError] = useState('');
  // The table's language; the lobby's choice until the first snapshot.
  const lang = snapshot?.lang ?? storedLang();
  const tr = (key: Key, params?: Params) => t(lang, key, params);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const run = (job: () => Promise<unknown>) => {
    setError('');
    job().catch((e: unknown) => {
      setError(e instanceof ApiError ? serverError(lang, e.message) : String(e));
    });
  };

  if (connection === 'gone' || snapshot?.phase === 'closed') {
    return (
      <main className="site-page">
        <p>{tr('tableClosed')}</p>
        <button type="button" className="button" onClick={() => go('/')}>
          {tr('backToLobby')}
        </button>
      </main>
    );
  }
  if (snapshot === null) {
    return (
      <main className="site-page">
        <p>{tr('connecting')}</p>
      </main>
    );
  }

  // The account confirmed in this tab (lobby), else a guest's nickname.
  const sit = (seat: number) =>
    run(async () => {
      const who = player();
      let name = nickname();
      if (!who && !name) {
        name = window.prompt(tr('nicknamePrompt'))?.trim() ?? '';
        if (!name) return;
        setNickname(name);
      }
      try {
        const {token: t} = await api.sit(tableId, seat, who ? {account: who} : {nickname: name});
        setToken(tableId, t);
        setLocalToken(t);
      } catch (e) {
        if (who && e instanceof ApiError && e.status === 401) {
          forgetAccount(who.username);
          setPlayer(undefined);
        }
        throw e;
      }
    });

  const leave = (seat: number) =>
    run(async () => {
      await api.emptySeat(tableId, seat, token);
      if (!snapshot.isCreator) {
        setToken(tableId, null);
        setLocalToken(null);
      }
    });

  const myTurn =
    snapshot.phase === 'playing' &&
    snapshot.you !== null &&
    snapshot.toMove === snapshot.you;
  const play = myTurn
    ? (action: number) => run(() => api.act(tableId, action, token))
    : null;

  return (
    <LangContext.Provider value={lang}>
      <main className="site-page site-page--table">
        <header className="site-header">
          <button type="button" className="button button--small" onClick={() => go('/')}>
            {tr('lobbyLink')}
          </button>
          <h1>{snapshot.name}</h1>
          <span className="site-badge">{phaseLabel(lang, snapshot.phase)}</span>
          {watch && <span className="site-badge">{tr('watchingBadge')}</span>}
          {connection !== 'live' && (
            <span className="site-badge site-badge--warn">{tr('reconnecting')}</span>
          )}
        </header>

        <p className="site-rotate-hint">{tr('rotateHint')}</p>

        {error && (
          <p className="site-error" role="alert">
            {error}
          </p>
        )}

        <div className="site-layout">
          <aside className="site-side">
            <Scoreboard snapshot={snapshot} />
            <Seats
              snapshot={snapshot}
              token={token}
              sit={sit}
              leave={leave}
              run={run}
              tableId={tableId}
              watch={watch}
            />
            {snapshot.isCreator && (
              <section className="site-card">
                {(snapshot.phase === 'open' || snapshot.phase === 'match_over') && (
                  <button
                    type="button"
                    className="button"
                    disabled={snapshot.seats.some(s => s.kind === 'empty')}
                    onClick={() => run(() => api.start(tableId, token))}
                  >
                    {snapshot.phase === 'open' ? tr('startMatch') : tr('newMatch')}
                  </button>
                )}{' '}
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => {
                    if (window.confirm(tr('closeTableConfirm'))) {
                      run(() => api.close(tableId, token));
                    }
                  }}
                >
                  {tr('closeTable')}
                </button>
              </section>
            )}
          </aside>

          <section className="site-game">
            <ThrowNotice snapshot={snapshot} />
            <ResultBanner snapshot={snapshot} tableId={tableId} token={token} run={run} />
            {snapshot.frame ? (
              // On phones what follows <Table> in .site-felt (the
              // .site-felt__actions bar) floats over the felt (site.css).
              <div className="site-felt">
                <Table snapshot={snapshot} play={play} />
                <ThrowBar snapshot={snapshot} tableId={tableId} token={token} run={run} />
              </div>
            ) : (
              <p className="site-card">
                {snapshot.isCreator ? tr('fillSeats') : tr('waitingForStart')}
              </p>
            )}
            <ScoreSheet snapshot={snapshot} />
          </section>
        </div>
      </main>
    </LangContext.Provider>
  );
}

function Table({
  snapshot,
  play,
}: {
  readonly snapshot: TableSnapshot;
  readonly play: ((action: number) => void) | null;
}): JSX.Element {
  const frame = snapshot.frame!;
  const lang = useLang();
  // Game seat g sits at table seat seatMap[g]. The trump and the bids are
  // drawn next to the names by the renderer.
  const labels = frame.seatMap.map(seat => {
    const s = snapshot.seats[seat];
    const name = seatName(lang, snapshot.seats, seat);
    return s?.kind === 'human' && !s.online ? t(lang, 'nameOffline', {name}) : name;
  });
  // Spectators see table seat 0 at the bottom.
  const bottomSeat = Math.max(0, frame.seatMap.indexOf(0));
  return (
    <SchnapsRenderer
      frame={frame}
      presentation={frame.presentation}
      play={play}
      seatLabels={labels}
      bottomSeat={bottomSeat}
    />
  );
}

function Scoreboard({snapshot}: {readonly snapshot: TableSnapshot}): JSX.Element {
  const m = snapshot.match;
  const lang = useLang();
  const tr = useT();
  // Pair ratings show while every seat is a logged-in user or a bot.
  const ratings = snapshot.ratings;
  const rated = ratings !== undefined && ratings[0] !== null && ratings[1] !== null;
  return (
    <section className="site-card" aria-label={tr('score')}>
      <h2>{m ? tr('setOfThree', {n: m.setNumber}) : tr('score')}</h2>
      <table className="site-score">
        <thead>
          <tr>
            <th>{tr('pair')}</th>
            <th>{tr('pointsToGo')}</th>
            <th>{tr('sets')}</th>
            {rated && <th>{tr('colRating')}</th>}
          </tr>
        </thead>
        <tbody>
          {[0, 1].map(p => (
            <tr key={p} data-winner={m?.winner === p ? 'true' : undefined}>
              <td>{pairNames(lang, p, snapshot.seats)}</td>
              <td className="site-score__need">{m ? m.need[p] : 31}</td>
              <td>{m ? m.sets[p] : 0}</td>
              {rated && <td className="site-score__rating">{ratings[p]}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {snapshot.dealer !== null && (
        <p className="site-muted">
          {tr('dealerIs', {name: seatName(lang, snapshot.seats, snapshot.dealer)})}
        </p>
      )}
    </section>
  );
}

function Seats({
  snapshot,
  token,
  sit,
  leave,
  run,
  tableId,
  watch,
}: {
  readonly snapshot: TableSnapshot;
  readonly token: string | null;
  readonly sit: (seat: number) => void;
  readonly leave: (seat: number) => void;
  readonly run: (job: () => Promise<unknown>) => void;
  readonly tableId: string;
  readonly watch: boolean;
}): JSX.Element {
  const lang = useLang();
  const tr = useT();
  // On the watch port nobody may sit.
  const seated = watch || snapshot.you !== null;
  return (
    <section className="site-card" aria-label={tr('seats')}>
      <h2>{tr('seats')}</h2>
      <ul className="site-seats">
        {snapshot.seats.map((s, i) => (
          <li key={i} className="site-seat">
            <span className="site-seat__where">{tr('seatN', {n: i + 1})}</span>
            <span className="site-seat__who">
              {s.kind === 'empty' ? (
                <em className="site-muted">{tr('empty')}</em>
              ) : (
                <>
                  <span
                    className="site-dot"
                    data-online={s.online ? 'true' : 'false'}
                    title={s.online ? tr('online') : tr('offline')}
                  />
                  {s.name}
                  {s.kind === 'bot' && (
                    <span className="site-muted">
                      {s.botLabel
                        ? ` ${tr('botOfKind', {label: botLabel(lang, s.botLabel)})}`
                        : tr('botSuffix')}
                    </span>
                  )}
                  {s.you && <strong> {tr('you')}</strong>}
                </>
              )}
            </span>
            <span className="site-seat__actions">
              {s.kind === 'empty' && !seated && (
                <button type="button" className="button button--small" onClick={() => sit(i)}>
                  {tr('sitHere')}
                </button>
              )}
              {snapshot.isCreator &&
                (s.kind === 'empty' || s.you) &&
                snapshot.bots.map(b => (
                  <button
                    key={b.name}
                    type="button"
                    className="button button--small"
                    onClick={() => run(() => api.setBot(tableId, i, b.name, token))}
                  >
                    {tr('addBot', {label: botLabel(lang, b.label)})}
                  </button>
                ))}
              {snapshot.isCreator && s.kind === 'bot' && (
                <button type="button" className="button button--small" onClick={() => leave(i)}>
                  {tr('removeBot')}
                </button>
              )}
              {s.you && snapshot.phase === 'open' && (
                <button type="button" className="button button--small" onClick={() => leave(i)}>
                  {tr('leave')}
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ResultBanner({
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
  const lang = useLang();
  const tr = useT();
  const r = snapshot.lastResult;
  if (r === null || (snapshot.phase !== 'deal_over' && snapshot.phase !== 'match_over')) {
    return null;
  }
  const d = r.deal;
  const declarer = d.declarer === null ? null : seatName(lang, snapshot.seats, d.declarer);
  const pair = (p: number) => pairNames(lang, p, snapshot.seats);
  return (
    <div className="site-result" role="status">
      <strong>
        {tr(d.points === 1 ? 'winPoint' : 'winPoints', {pair: pair(d.winner), n: d.points})}
      </strong>
      <span>
        {contractText(lang, d.contract, d.flecks)}
        {declarer ? tr('byDeclarer', {name: declarer}) : ''}
      </span>
      <span>
        {tr('toGo')} {pair(0)} {d.need_after[0]} · {pair(1)} {d.need_after[1]}
      </span>
      {r.setWinner !== null && (
        <strong>{tr('setTo', {n: d.set_number, pair: pair(r.setWinner)})}</strong>
      )}
      {r.matchWinner !== null && <strong>{tr('matchTo', {pair: pair(r.matchWinner)})}</strong>}
      {r.setWinner !== null && r.rating && (
        <span className="site-result__rating">{setRatingText(lang, r.rating, pair)}</span>
      )}
      {snapshot.phase === 'deal_over' && (
        <WaitControl snapshot={snapshot} tableId={tableId} token={token} run={run} />
      )}
    </div>
  );
}

/** A finished set's rating change ("Anna & Ron: 600 → 616 (+16) · …"), or
 *  why it was not rated. */
function setRatingText(lang: Lang, rating: SetRating, pair: (p: number) => string): string {
  const {before, after} = rating;
  if (!rating.rated || !before || !after) return unratedText(lang, rating.unrated);
  return [0, 1]
    .map(p => {
      const from = before[p] ?? 0;
      const to = after[p] ?? 0;
      return t(lang, 'ratingMove', {pair: pair(p), from, to, delta: signed(to - from)});
    })
    .join(' · ');
}

/**
 * Between deals: who holds the next deal back, and the seated player's
 * Wait / Continue toggle (Table.wait on the server).
 */
function WaitControl({
  snapshot,
  tableId,
  token,
  run,
}: {
  readonly snapshot: TableSnapshot;
  readonly tableId: string;
  readonly token: string | null;
  readonly run: (job: () => Promise<unknown>) => void;
}): JSX.Element {
  const lang = useLang();
  const tr = useT();
  const waiting = snapshot.waiting ?? [];
  const me = snapshot.you;
  const mine = me !== null && waiting.includes(me);
  const names = waiting.map(seat => seatName(lang, snapshot.seats, seat)).join(', ');
  return (
    <span className="site-wait">
      <span className="site-muted">
        {waiting.length > 0 ? tr('waitingFor', {names}) : tr('nextDeal')}
      </span>
      {me !== null && !snapshot.reveal && (
        <button
          type="button"
          className="button button--small"
          aria-pressed={mine}
          onClick={() => run(() => api.wait(tableId, !mine, token))}
        >
          {tr(mine ? 'waitRelease' : 'waitButton')}
        </button>
      )}
    </span>
  );
}

function ScoreSheet({snapshot}: {readonly snapshot: TableSnapshot}): JSX.Element | null {
  const lang = useLang();
  const tr = useT();
  const deals = snapshot.match?.deals ?? [];
  if (deals.length === 0) return null;
  const name = (seat: number | null) =>
    seat === null ? '—' : seatName(lang, snapshot.seats, seat);
  return (
    <section className="site-card" aria-label={tr('scoreSheet')}>
      <h2>{tr('scoreSheet')}</h2>
      <table className="site-sheet">
        <thead>
          <tr>
            <th>{tr('colNumber')}</th>
            <th>{tr('colSet')}</th>
            <th>{tr('colDealer')}</th>
            <th>{tr('colContract')}</th>
            <th>{tr('colDeclarer')}</th>
            <th>{tr('colWonBy')}</th>
            <th>{tr('colPoints')}</th>
            <th>{pairNames(lang, 0, snapshot.seats)}</th>
            <th>{pairNames(lang, 1, snapshot.seats)}</th>
          </tr>
        </thead>
        <tbody>
          {[...deals].reverse().map(d => (
            <tr key={d.number}>
              <td>{d.number}</td>
              <td>{d.set_number}</td>
              <td>{name(d.dealer)}</td>
              <td>
                {contractText(lang, d.contract, d.flecks)}
                {d.throw ? ` · ${throwMark(tr, d.throw)} (${name(d.throw.seat)})` : ''}
              </td>
              <td>{name(d.declarer)}</td>
              <td>{pairNames(lang, d.winner, snapshot.seats)}</td>
              <td>{d.points}</td>
              <td>{d.need_after[0]}</td>
              <td>{d.need_after[1]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
