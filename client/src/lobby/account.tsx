// The lobby's player card: who plays in this tab.
//
// - Confirmed account: "Playing as Anna", with Switch player and Log out.
// - Accounts remembered on this device but nobody confirmed in this tab:
//   "Who's playing?" with one button per account (no password) and a guest
//   button.
// - A guest: the nickname box, as before accounts existed (unrated).
// Log in or register opens a small username + password form; a login
// remembers the account on this device (net/accounts.ts).
// - The account "admin" also gets Download / Upload database buttons.

import {type JSX, useRef, useState} from 'react';

import type {Key, Params} from '../i18n/strings.ts';
import {
  type Account,
  accounts as loadAccounts,
  api,
  ApiError,
  forgetAccount,
  isAdmin,
  rememberAccount,
} from '../net/api.ts';

export function AccountCard({
  tr,
  who,
  choose,
  nick,
  setNick,
  run,
}: {
  readonly tr: (key: Key, params?: Params) => string;
  /** Who plays in this tab: an account, null (a guest), undefined (ask). */
  readonly who: Account | null | undefined;
  readonly choose: (who: Account | null | undefined) => void;
  /** The guest's nickname. */
  readonly nick: string;
  readonly setNick: (name: string, done?: boolean) => void;
  readonly run: (job: () => Promise<void>) => void;
}): JSX.Element {
  // Read on every render: logging in or out re-renders through choose().
  const list = loadAccounts();
  const [form, setForm] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);

  const download = (a: Account) =>
    run(async () => {
      const {blob, name} = await api.downloadDatabase(a.key);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    });

  const upload = (a: Account, file: File | undefined) => {
    if (fileInput.current) fileInput.current.value = '';
    if (!file || !window.confirm(tr('adminUploadConfirm', {file: file.name}))) return;
    run(async () => {
      const n = await api.uploadDatabase(a.key, file);
      window.alert(tr('adminUploaded', {users: n.users, pairs: n.pairs, sets: n.sets}));
    });
  };

  const pick = (a: Account) =>
    run(async () => {
      try {
        await api.me(a.key);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) forgetAccount(a.username);
        throw e;
      }
      choose(a);
    });

  const enter = (how: 'login' | 'register') =>
    run(async () => {
      if (!username.trim() || !password) throw new ApiError('enterUserAndPassword');
      const a = await (how === 'login' ? api.login : api.register)(username, password);
      rememberAccount(a);
      setForm(false);
      setUsername('');
      setPassword('');
      choose(a);
    });

  const logOut = (a: Account) => {
    if (!window.confirm(tr('logOutConfirm', {name: a.username}))) return;
    api.logout(a.key).catch(() => {});
    forgetAccount(a.username);
    choose(undefined);
  };

  const loginForm = form ? (
    <form
      className="site-row site-account__form"
      onSubmit={e => {
        e.preventDefault();
        enter('login');
      }}
    >
      <label className="site-field">
        <span>{tr('username')}</span>
        <input
          value={username}
          maxLength={20}
          autoComplete="username"
          onChange={e => setUsername(e.target.value)}
        />
      </label>
      <label className="site-field">
        <span>{tr('password')}</span>
        <input
          type="password"
          value={password}
          autoComplete="current-password"
          onChange={e => setPassword(e.target.value)}
        />
      </label>
      <button type="submit" className="button">
        {tr('logIn')}
      </button>
      <button type="button" className="button" onClick={() => enter('register')}>
        {tr('register')}
      </button>
      <button type="button" className="button button--small" onClick={() => setForm(false)}>
        {tr('cancel')}
      </button>
    </form>
  ) : (
    <button type="button" className="button button--small" onClick={() => setForm(true)}>
      {tr('logInOrRegister')}
    </button>
  );

  if (who) {
    return (
      <section className="site-card site-account">
        <h2>{tr('player')}</h2>
        <div className="site-row">
          <strong className="site-account__who">{tr('playingAs', {name: who.username})}</strong>
          <button type="button" className="button button--small" onClick={() => choose(undefined)}>
            {tr('switchPlayer')}
          </button>
          <button type="button" className="button button--small" onClick={() => logOut(who)}>
            {tr('logOut')}
          </button>
        </div>
        {isAdmin(who.username) && (
          <div className="site-row">
            <span className="site-muted">{tr('adminDatabase')}</span>
            <button type="button" className="button button--small" onClick={() => download(who)}>
              {tr('adminDownload')}
            </button>
            <button
              type="button"
              className="button button--small"
              onClick={() => fileInput.current?.click()}
            >
              {tr('adminUpload')}
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".db,.sqlite,.sqlite3,application/vnd.sqlite3"
              hidden
              onChange={e => upload(who, e.target.files?.[0])}
            />
          </div>
        )}
      </section>
    );
  }

  if (who === undefined && list.length > 0) {
    return (
      <section className="site-card site-account">
        <h2>{tr('whoIsPlaying')}</h2>
        <div className="site-row">
          {list.map(a => (
            <button key={a.username} type="button" className="button" onClick={() => pick(a)}>
              {a.username}
            </button>
          ))}
          <button type="button" className="button button--small" onClick={() => choose(null)}>
            {tr('playAsGuest')}
          </button>
        </div>
        <div className="site-account__more">{loginForm}</div>
      </section>
    );
  }

  return (
    <section className="site-card site-account">
      <label className="site-field">
        <span>{tr('yourNickname')}</span>
        <input
          value={nick}
          maxLength={20}
          onChange={e => setNick(e.target.value)}
          onBlur={() => setNick(nick, true)}
          placeholder={tr('nicknameExample')}
        />
      </label>
      <p className="site-muted">
        {tr('guestHint')}{' '}
        {list.length > 0 && (
          <button type="button" className="button button--small" onClick={() => choose(undefined)}>
            {tr('switchPlayer')}
          </button>
        )}
      </p>
      <div className="site-account__more">{loginForm}</div>
    </section>
  );
}
