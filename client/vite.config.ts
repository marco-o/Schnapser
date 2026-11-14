import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

// `npm run dev` sends API and WebSocket requests to the site's server.
const SERVER = process.env['SCHNAPS_WEB_SERVER'] ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {target: SERVER},
      '/ws': {target: SERVER.replace(/^http/, 'ws'), ws: true},
    },
  },
});
