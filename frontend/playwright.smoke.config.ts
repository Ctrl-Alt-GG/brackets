import { defineConfig } from '@playwright/test';

import { ORGANIZER } from './tests/smoke/organizer';

/**
 * The frontend against the real API, through the dev server's proxy, so the page and the API share
 * an origin as in production. PG_DSN and JWT_SECRET come from the environment. The API sets up an
 * empty database when it starts, with the organizer the tests sign in as.
 */
export default defineConfig({
  testDir: './tests/smoke',
  testMatch: '**/*.smoke.ts',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5189', headless: true },
  webServer: [
    {
      command: 'uv run --locked uvicorn bracket.app:app --host 127.0.0.1 --port 8400',
      cwd: '../backend',
      env: {
        ADMIN_EMAIL: ORGANIZER.email,
        ADMIN_PASSWORD: ORGANIZER.password,
        API_PREFIX: '/api',
        ENVIRONMENT: 'DEVELOPMENT',
      },
      reuseExistingServer: false,
      url: 'http://127.0.0.1:8400/api/ping',
    },
    {
      command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5189 --strictPort`,
      reuseExistingServer: false,
      url: 'http://127.0.0.1:5189',
    },
  ],
});
