// One table: the scoreboard, the seats (with the creator's bot controls),
// the card table (the copied OpenSpiel schnaps renderer), the result of the
// last deal and the score sheet.

import {type JSX, useState} from 'react';

import {SchnapsRenderer} from '../gui/games/schnaps/schnaps_renderer.tsx';
import {
  api,
  ApiError,
  nickname,
  setNickname,
  setToken,
  type TableSnapshot,
  tokenOf,
} from '../net/api.ts';
import {useTable} from '../net/use_table.ts';
import {contractText, pairNames, phaseLabel, seatName} from './labels.ts';

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

  const run = (job: () => Promise<unknown>) => {
    setError('');
    job().catch((e: unknown) => {
      setError(e instanceof ApiError ? e.message : String(e));
    });
  };

  if (connection === 'gone' || snapshot?.phase === 'closed') {
    return (
      <main className="site-page">
        <p>This table is closed.</p>
        <button type="button" className="button" onClick={() => go('/')}>
          Back to the lobby
        </button>
      </main>
    );
  }
  if (snapshot === null) {
    return (
      <main className="site-page">
        <p>Connecting…</p>
      </main>
    );
  }

  const sit = (seat: number) =>
    run(async () => {
      let name = nickname();
      if (!name) {
        name = window.prompt('Your nickname?')?.trim() ?? '';
        if (!name) return;
        setNickname(name);
      }
      const {token: t} = await api.sit(tableId, seat, name);
      setToken(tableId, t);
      setLocalToken(t);
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
    <main className="site-page site-page--table">
      <header className="site-header">
        <button type="button" className="button button--small" onClick={() => go('/')}>
          ← Lobby
        </button>
        <h1>{snapshot.name}</h1>
        <span className="site-badge">{phaseLabel(snapshot.phase)}</span>
        {watch && <span className="site-badge">watching · all cards shown</span>}
        {connection !== 'live' && (
          <span className="site-badge site-badge--warn">reconnecting…</span>
        )}
      </header>

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
                  {snapshot.phase === 'open' ? 'Start match' : 'New match'}
                </button>
              )}{' '}
              <button
                type="button"
                className="button button--small"
                onClick={() => {
                  if (window.confirm('Close this table for everyone?')) {
                    run(() => api.close(tableId, token));
                  }
                }}
              >
                Close table
              </button>
            </section>
          )}
        </aside>

        <section className="site-game">
          <ResultBanner snapshot={snapshot} />
          {snapshot.frame ? (
            <Table snapshot={snapshot} play={play} />
          ) : (
            <p className="site-card">
              {snapshot.isCreator
                ? 'Fill the empty seats (players or bots), then start the match.'
                : 'Waiting for the table to start.'}
            </p>
          )}
          <ScoreSheet snapshot={snapshot} />
        </section>
      </div>
    </main>
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
  // Game seat g sits at table seat seatMap[g]. The trump and the bids are
  // drawn next to the names by the renderer.
  const labels = frame.seatMap.map(t => {
    const s = snapshot.seats[t];
    const name = seatName(snapshot.seats, t);
    return s?.kind === 'human' && !s.online ? `${name} · offline` : name;
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
  return (
    <section className="site-card" aria-label="Score">
      <h2>{m ? `Set ${m.setNumber} · best of 3` : 'Score'}</h2>
      <table className="site-score">
        <thead>
          <tr>
            <th>Pair</th>
            <th>Points to go</th>
            <th>Sets</th>
          </tr>
        </thead>
        <tbody>
          {[0, 1].map(p => (
            <tr key={p} data-winner={m?.winner === p ? 'true' : undefined}>
              <td>{pairNames(p, snapshot.seats)}</td>
              <td className="site-score__need">{m ? m.need[p] : 31}</td>
              <td>{m ? m.sets[p] : 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {snapshot.dealer !== null && (
        <p className="site-muted">
          Dealer: {seatName(snapshot.seats, snapshot.dealer)}
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
  // On the watch port nobody may sit.
  const seated = watch || snapshot.you !== null;
  return (
    <section className="site-card" aria-label="Seats">
      <h2>Seats</h2>
      <ul className="site-seats">
        {snapshot.seats.map((s, i) => (
          <li key={i} className="site-seat">
            <span className="site-seat__where">Seat {i + 1}</span>
            <span className="site-seat__who">
              {s.kind === 'empty' ? (
                <em className="site-muted">empty</em>
              ) : (
                <>
                  <span
                    className="site-dot"
                    data-online={s.online ? 'true' : 'false'}
                    title={s.online ? 'online' : 'offline'}
                  />
                  {s.name}
                  {s.kind === 'bot' && (
                    <span className="site-muted"> ({s.botLabel ?? 'bot'} bot)</span>
                  )}
                  {s.you && <strong> (you)</strong>}
                </>
              )}
            </span>
            <span className="site-seat__actions">
              {s.kind === 'empty' && !seated && (
                <button type="button" className="button button--small" onClick={() => sit(i)}>
                  Sit here
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
                    + {b.label}
                  </button>
                ))}
              {snapshot.isCreator && s.kind === 'bot' && (
                <button type="button" className="button button--small" onClick={() => leave(i)}>
                  Remove bot
                </button>
              )}
              {s.you && snapshot.phase === 'open' && (
                <button type="button" className="button button--small" onClick={() => leave(i)}>
                  Leave
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ResultBanner({snapshot}: {readonly snapshot: TableSnapshot}): JSX.Element | null {
  const r = snapshot.lastResult;
  if (r === null || (snapshot.phase !== 'deal_over' && snapshot.phase !== 'match_over')) {
    return null;
  }
  const d = r.deal;
  const declarer = d.declarer === null ? null : seatName(snapshot.seats, d.declarer);
  return (
    <div className="site-result" role="status">
      <strong>
        {pairNames(d.winner, snapshot.seats)} win {d.points} point{d.points === 1 ? '' : 's'}
      </strong>
      <span>
        {contractText(d.contract, d.flecks)}
        {declarer ? ` by ${declarer}` : ''}
      </span>
      <span>
        To go: {pairNames(0, snapshot.seats)} {d.need_after[0]} ·{' '}
        {pairNames(1, snapshot.seats)} {d.need_after[1]}
      </span>
      {r.setWinner !== null && (
        <strong>Set {d.set_number} to {pairNames(r.setWinner, snapshot.seats)}!</strong>
      )}
      {r.matchWinner !== null && (
        <strong>Match to {pairNames(r.matchWinner, snapshot.seats)}!</strong>
      )}
      {snapshot.phase === 'deal_over' && <span className="site-muted">Next deal in a moment…</span>}
    </div>
  );
}

function ScoreSheet({snapshot}: {readonly snapshot: TableSnapshot}): JSX.Element | null {
  const deals = snapshot.match?.deals ?? [];
  if (deals.length === 0) return null;
  const name = (seat: number | null) =>
    seat === null ? '—' : seatName(snapshot.seats, seat);
  return (
    <section className="site-card" aria-label="Score sheet">
      <h2>Score sheet</h2>
      <table className="site-sheet">
        <thead>
          <tr>
            <th>#</th>
            <th>Set</th>
            <th>Dealer</th>
            <th>Contract</th>
            <th>Declarer</th>
            <th>Won by</th>
            <th>Pts</th>
            <th>{pairNames(0, snapshot.seats)}</th>
            <th>{pairNames(1, snapshot.seats)}</th>
          </tr>
        </thead>
        <tbody>
          {[...deals].reverse().map(d => (
            <tr key={d.number}>
              <td>{d.number}</td>
              <td>{d.set_number}</td>
              <td>{name(d.dealer)}</td>
              <td>{contractText(d.contract, d.flecks)}</td>
              <td>{name(d.declarer)}</td>
              <td>{pairNames(d.winner, snapshot.seats)}</td>
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
