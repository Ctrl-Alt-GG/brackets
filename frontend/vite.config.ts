import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';

import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          // Every page needs React and the router, and they change less often than the app, so a
          // chunk of their own stays cached across releases.
          groups: [
            {
              name: 'react',
              test: /[\\/]node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/,
            },
          ],
        },
      },
    },
  },
  plugins: [react(), tailwindcss()],
  server: {
    // The API answers on the page's own origin, as in production, so its session cookie works
    // without cross-origin requests.
    proxy: { '/api': 'http://localhost:8400' },
  },
});
