// The table's live snapshot over its WebSocket, reconnecting by itself.

import {useEffect, useState} from 'react';

import type {TableSnapshot} from './api.ts';

export type Connection = 'connecting' | 'live' | 'lost' | 'gone';

export function useTable(
  tableId: string,
  token: string | null,
): {snapshot: TableSnapshot | null; connection: Connection} {
  const [snapshot, setSnapshot] = useState<TableSnapshot | null>(null);
  const [connection, setConnection] = useState<Connection>('connecting');

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let ping: number | undefined;
    let stopped = false;

    const open = () => {
      const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
      const query = token ? `?token=${encodeURIComponent(token)}` : '';
      socket = new WebSocket(
        `${scheme}://${location.host}/ws/tables/${tableId}${query}`,
      );
      socket.onopen = () => {
        setConnection('live');
        ping = window.setInterval(() => socket?.send('ping'), 25000);
      };
      socket.onmessage = event => {
        setSnapshot(JSON.parse(String(event.data)) as TableSnapshot);
      };
      socket.onclose = event => {
        window.clearInterval(ping);
        if (stopped) return;
        if (event.code === 4404) {
          setConnection('gone');
          return;
        }
        setConnection('lost');
        retry = window.setTimeout(open, 2000);
      };
    };
    open();
    return () => {
      stopped = true;
      window.clearTimeout(retry);
      window.clearInterval(ping);
      socket?.close();
    };
  }, [tableId, token]);

  return {snapshot, connection};
}
