import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  testMatch: '**/*.browser.ts',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5188', headless: true },
  webServer: {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5188 --strictPort`,
    url: 'http://127.0.0.1:5188',
    reuseExistingServer: !process.env.CI,
  },
});
