// The Schnaps site's client: the lobby at /, a table at /table/<id>.

import {type JSX, StrictMode, useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';

import './gui/styles/tokens.css';
import './gui/styles/base.css';
import './site.css';

import {Lobby} from './lobby/lobby.tsx';
import {api} from './net/api.ts';
import {TablePage} from './table/table_page.tsx';

function App(): JSX.Element {
  const [path, setPath] = useState(location.pathname);
  // The all-cards watch port (server: create_watch_app) is read-only.
  const [watch, setWatch] = useState<boolean | null>(null);
  useEffect(() => {
    api
      .site()
      .then(s => setWatch(s.watch))
      .catch(() => setWatch(false));
  }, []);
  useEffect(() => {
    const onPop = () => setPath(location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const go = (to: string) => {
    history.pushState(null, '', to);
    setPath(to);
  };
  if (watch === null) return <main className="site-page" />;
  const match = /^\/table\/([\w-]+)$/.exec(path);
  if (match?.[1]) {
    return <TablePage key={match[1]} tableId={match[1]} go={go} watch={watch} />;
  }
  return <Lobby go={go} watch={watch} />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
