// The lobby: the language, your nickname, the tables (refreshed every few
// seconds), a form to start a table, and a free seat to take at any table.
// The lobby shows the language picked here (Italian until one is picked); a
// table started here keeps that language for everyone at it.

import {type JSX, useEffect, useState} from 'react';

import {storedLang, storeLang} from '../i18n/lang.tsx';
import {
  type Key,
  type Lang,
  LANG_NAMES,
  LANGS,
  type Params,
  serverError,
  STRINGS,
  t,
} from '../i18n/strings.ts';

import {
  api,
  ApiError,
  nickname,
  setNickname,
  setToken,
  type TableSummary,
  tokenOf,
} from '../net/api.ts';
import {SEAT_NUMBERS, pairNames, phaseLabel, seatChoice} from '../table/labels.ts';

export function Lobby({
  go,
  watch,
}: {
  readonly go: (path: string) => void;
  /** The all-cards watch port: no seats to take, no tables to start. */
  readonly watch: boolean;
}): JSX.Element {
  const [name, setName] = useState(nickname());
  const [tables, setTables] = useState<TableSummary[] | null>(null);
  const [tableName, setTableName] = useState('');
  const [seat, setSeat] = useState(0);
  const [error, setError] = useState('');
  const [lang, setLang] = useState<Lang>(storedLang());
  const tr = (key: Key, params?: Params) => t(lang, key, params);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const pickLang = (l: Lang) => {
    setLang(l);
    storeLang(l);
  };

  useEffect(() => {
    let stopped = false;
    const load = () => {
      api
        .tables()
        .then(t => {
          if (!stopped) setTables(t);
        })
        .catch(() => {
          if (!stopped) setError('serverUnreachable');
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
      setError('enterNicknameFirst');
      return null;
    }
    setNickname(n);
    return n;
  };

  const run = (job: () => Promise<void>) => {
    setError('');
    job().catch((e: unknown) => {
      setError(e instanceof ApiError ? serverError(lang, e.message) : String(e));
    });
  };

  const create = () =>
    run(async () => {
      const player = needName();
      if (player === null) return;
      const title = tableName.trim() || tr('defaultTableName', {player});
      const {id, token} = await api.create(title, player, seat, lang);
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
      <h1 className="site-title">
        {tr('siteTitle')}
        {watch ? ` · ${tr('watchingTitle')}` : ''}
      </h1>
      <section className="site-card">
        <label className="site-field">
          <span>{watch ? tr('language') : tr('tableLanguage')}</span>
          <select value={lang} onChange={e => pickLang(e.target.value as Lang)}>
            {LANGS.map(l => (
              <option key={l} value={l}>
                {LANG_NAMES[l]}
              </option>
            ))}
          </select>
        </label>
      </section>
      {!watch && (<>
      <section className="site-card">
        <label className="site-field">
          <span>{tr('yourNickname')}</span>
          <input
            value={name}
            maxLength={20}
            onChange={e => setName(e.target.value)}
            onBlur={() => name.trim() && setNickname(name.trim())}
            placeholder={tr('nicknameExample')}
          />
        </label>
      </section>

      <section className="site-card">
        <h2>{tr('startATable')}</h2>
        <div className="site-row">
          <label className="site-field">
            <span>{tr('tableName')}</span>
            <input
              value={tableName}
              maxLength={20}
              onChange={e => setTableName(e.target.value)}
              placeholder={tr('tableNameExample')}
            />
          </label>
          <label className="site-field">
            <span>{tr('yourSeat')}</span>
            <select value={seat} onChange={e => setSeat(Number(e.target.value))}>
              {SEAT_NUMBERS.map(i => (
                <option key={i} value={i}>
                  {seatChoice(lang, i)}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="button" onClick={create}>
            {tr('startTable')}
          </button>
        </div>
      </section>
      </>)}

      {error && (
        <p className="site-error" role="alert">
          {/* Our own messages are keys; the server's arrive translated. */}
          {Object.hasOwn(STRINGS, error) ? tr(error as Key) : error}
        </p>
      )}

      <section className="site-card">
        <h2>{tr('tables')}</h2>
        {tables === null ? (
          <p>{tr('loading')}</p>
        ) : tables.length === 0 ? (
          <p>{watch ? tr('noTables') : tr('noTablesStartOne')}</p>
        ) : (
          <ul className="site-tables">
            {tables.map(t => {
              const mine = tokenOf(t.id) !== null;
              return (
                <li key={t.id} className="site-table">
                  <div className="site-table__head">
                    <strong>{t.name}</strong>
                    <span className="site-badge">{phaseLabel(lang, t.phase)}</span>
                    <span className="site-badge" title={tr('tableLanguage')}>
                      {LANG_NAMES[t.lang] ?? t.lang}
                    </span>
                    {t.need && t.sets && (
                      <span className="site-muted">
                        {pairNames(lang, 0, t.seats)} {t.need[0]} ({setsText(lang, t.sets[0])}) ·{' '}
                        {pairNames(lang, 1, t.seats)} {t.need[1]} ({setsText(lang, t.sets[1])})
                      </span>
                    )}
                  </div>
                  <ol className="site-table__seats">
                    {t.seats.map((s, i) => (
                      <li key={i}>
                        <span className="site-muted">{tr('seatN', {n: i + 1})}:</span>{' '}
                        {s.kind === 'empty' && watch ? (
                          <em className="site-muted">{tr('empty')}</em>
                        ) : s.kind === 'empty' ? (
                          <button
                            type="button"
                            className="button button--small"
                            onClick={() => sit(t, i)}
                          >
                            {tr('sitHere')}
                          </button>
                        ) : (
                          <span>
                            {s.name}
                            {s.kind === 'bot' ? tr('botSuffix') : ''}
                            {s.kind === 'human' && !s.online ? tr('offlineSuffix') : ''}
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
                    {mine && !watch ? tr('backToMySeat') : tr('watch')}
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

/** "2 sets", in `lang`. */
function setsText(lang: Lang, n: number | undefined): string {
  return n === 1 ? t(lang, 'setsCountOne') : t(lang, 'setsCount', {n: n ?? 0});
}
