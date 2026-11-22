// The lobby's ratings: every rated pair, best first (GET /api/ratings).
// A logged-in player's own pairs are highlighted and can be shown alone.

import {type JSX, useState} from 'react';

import type {Key, Lang, Params} from '../i18n/strings.ts';
import type {PairStanding} from '../net/api.ts';
import {standingName} from '../table/labels.ts';

export function RatingsCard({
  lang,
  tr,
  standings,
  me,
}: {
  readonly lang: Lang;
  readonly tr: (key: Key, params?: Params) => string;
  /** null while loading. */
  readonly standings: readonly PairStanding[] | null;
  /** The username playing in this tab, or null. */
  readonly me: string | null;
}): JSX.Element {
  const [onlyMine, setOnlyMine] = useState(false);
  const mine = (p: PairStanding) =>
    me !== null && p.players.some(x => !x.bot && x.name.toLowerCase() === me.toLowerCase());
  const rows = (standings ?? [])
    .map((p, i) => ({p, rank: i + 1}))
    .filter(({p}) => !onlyMine || mine(p));
  return (
    <section className="site-card" aria-label={tr('ratings')}>
      <h2>{tr('ratings')}</h2>
      <p className="site-muted">{tr('ratingsIntro')}</p>
      {standings === null ? (
        <p>{tr('loading')}</p>
      ) : standings.length === 0 ? (
        <p>{tr('noRatings')}</p>
      ) : (
        <>
          {me !== null && (
            <label className="site-check">
              <input
                type="checkbox"
                checked={onlyMine}
                onChange={e => setOnlyMine(e.target.checked)}
              />{' '}
              {tr('onlyMine')}
            </label>
          )}
          <table className="site-score site-ratings">
            <thead>
              <tr>
                <th>{tr('colNumber')}</th>
                <th>{tr('pair')}</th>
                <th>{tr('colRating')}</th>
                <th>{tr('colWonLost')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({p, rank}) => (
                <tr key={p.key} data-mine={mine(p) ? 'true' : undefined}>
                  <td>{rank}</td>
                  <td>{standingName(lang, p.players)}</td>
                  <td className="site-ratings__value">{p.rating}</td>
                  <td>
                    {p.won}–{p.lost}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
