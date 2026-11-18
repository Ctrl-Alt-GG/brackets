import { defineConfig } from '@playwright/test';

/**
 * The production image, as nginx serves it. CI builds the image and starts it at BRACKET_IMAGE_URL,
 * with API_BASE_URL set to that same address: the tests answer the page's API requests.
 */
export default defineConfig({
  testDir: './tests/image',
  testMatch: '**/*.image.ts',
  workers: 1,
  use: { baseURL: process.env.BRACKET_IMAGE_URL ?? 'http://127.0.0.1:8080', headless: true },
});
