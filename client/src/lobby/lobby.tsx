// The lobby: your nickname, the tables (refreshed every few seconds), a
// form to start a table, and a free seat to take at any table.

import {type JSX, useEffect, useState} from 'react';

import {
  api,
  ApiError,
  nickname,
  setNickname,
  setToken,
  type TableSummary,
  tokenOf,
} from '../net/api.ts';
import {SEAT_NAMES, pairLabel, phaseLabel} from '../table/labels.ts';

export function Lobby({go}: {readonly go: (path: string) => void}): JSX.Element {
  const [name, setName] = useState(nickname());
  const [tables, setTables] = useState<TableSummary[] | null>(null);
  const [tableName, setTableName] = useState('');
  const [seat, setSeat] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    let stopped = false;
    const load = () => {
      api
        .tables()
        .then(t => {
          if (!stopped) setTables(t);
        })
        .catch(() => {
          if (!stopped) setError('The server is not reachable.');
        });
    };
    load();
    const timer = window.setInterval(load, 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  const needName = (): string | null => {
    const n = name.trim();
    if (!n) {
      setError('Enter your nickname first.');
      return null;
    }
    setNickname(n);
    return n;
  };

  const run = (job: () => Promise<void>) => {
    setError('');
    job().catch((e: unknown) => {
      setError(e instanceof ApiError ? e.message : String(e));
    });
  };

  const create = () =>
    run(async () => {
      const player = needName();
      if (player === null) return;
      const title = tableName.trim() || `${player}'s table`;
      const {id, token} = await api.create(title, player, seat);
      setToken(id, token);
      go(`/table/${id}`);
    });

  const sit = (table: TableSummary, s: number) =>
    run(async () => {
      const player = needName();
      if (player === null) return;
      const {token} = await api.sit(table.id, s, player);
      setToken(table.id, token);
      go(`/table/${table.id}`);
    });

  return (
    <main className="site-page">
      <h1 className="site-title">Schnaps</h1>
      <section className="site-card">
        <label className="site-field">
          <span>Your nickname</span>
          <input
            value={name}
            maxLength={20}
            onChange={e => setName(e.target.value)}
            onBlur={() => name.trim() && setNickname(name.trim())}
            placeholder="e.g. Anna"
          />
        </label>
      </section>

      <section className="site-card">
        <h2>Start a table</h2>
        <div className="site-row">
          <label className="site-field">
            <span>Table name</span>
            <input
              value={tableName}
              maxLength={20}
              onChange={e => setTableName(e.target.value)}
              placeholder="Stammtisch"
            />
          </label>
          <label className="site-field">
            <span>Your seat</span>
            <select value={seat} onChange={e => setSeat(Number(e.target.value))}>
              {SEAT_NAMES.map((n, i) => (
                <option key={n} value={i}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="button" onClick={create}>
            Start table
          </button>
        </div>
      </section>

      {error && (
        <p className="site-error" role="alert">
          {error}
        </p>
      )}

      <section className="site-card">
        <h2>Tables</h2>
        {tables === null ? (
          <p>Loading…</p>
        ) : tables.length === 0 ? (
          <p>No tables yet. Start one above.</p>
        ) : (
          <ul className="site-tables">
            {tables.map(t => {
              const mine = tokenOf(t.id) !== null;
              return (
                <li key={t.id} className="site-table">
                  <div className="site-table__head">
                    <strong>{t.name}</strong>
                    <span className="site-badge">{phaseLabel(t.phase)}</span>
                    {t.need && t.sets && (
                      <span className="site-muted">
                        {pairLabel(0)} {t.need[0]} ({t.sets[0]} sets) ·{' '}
                        {pairLabel(1)} {t.need[1]} ({t.sets[1]} sets)
                      </span>
                    )}
                  </div>
                  <ol className="site-table__seats">
                    {t.seats.map((s, i) => (
                      <li key={i}>
                        <span className="site-muted">{SEAT_NAMES[i]}:</span>{' '}
                        {s.kind === 'empty' ? (
                          <button
                            type="button"
                            className="button button--small"
                            onClick={() => sit(t, i)}
                          >
                            Sit here
                          </button>
                        ) : (
                          <span>
                            {s.name}
                            {s.kind === 'bot' ? ' (bot)' : ''}
                            {s.kind === 'human' && !s.online ? ' (offline)' : ''}
                          </span>
                        )}
                      </li>
                    ))}
                  </ol>
                  <button
                    type="button"
                    className="button button--small"
                    onClick={() => go(`/table/${t.id}`)}
                  >
                    {mine ? 'Back to my seat' : 'Watch'}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </main>
  );
}
