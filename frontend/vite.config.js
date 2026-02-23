import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/institutions': 'http://127.0.0.1:8000',
      '/health':       'http://127.0.0.1:8000',
      '/search':       'http://127.0.0.1:8000',
      '/tickers':      'http://127.0.0.1:8000',
    },
  },
  build: { outDir: 'dist' },
});
