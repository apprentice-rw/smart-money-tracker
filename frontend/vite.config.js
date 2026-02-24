import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const API_PORT   = process.env.VITE_API_PORT ?? '8000';
const API_ORIGIN = `http://127.0.0.1:${API_PORT}`;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/institutions': API_ORIGIN,
      '/health':       API_ORIGIN,
      '/search':       API_ORIGIN,
      '/tickers':      API_ORIGIN,
      '/stock':        API_ORIGIN,
    },
  },
  build: { outDir: 'dist' },
});
