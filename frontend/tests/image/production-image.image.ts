import { expect, test } from '@playwright/test';

import type * as OpenApi from '../../src/openapi';
import { bracket, ranking, stage, teams, tournament } from '../browser/fixtures';

test('the page gets the API origin it was started with, and may connect to it', async ({
  baseURL,
  request,
}) => {
  const config = await request.get('/runtime-config.js');
  expect(config.headers()['cache-control']).toBe('no-store');
  expect(await config.text()).toContain(`apiBaseUrl: "${baseURL}"`);

  const headers = (await request.get('/')).headers();
  expect(headers['content-security-policy']).toContain(`connect-src 'self' ${baseURL};`);
  expect(headers['content-security-policy']).toContain("script-src 'self';");
  expect(headers['x-frame-options']).toBe('DENY');
});

test('a deep link gets the app, whose built files are cached for good', async ({ request }) => {
  const deepLink = await request.get('/tournaments/7/dashboard/bracket');
  expect(deepLink.status()).toBe(200);
  expect(deepLink.headers()['cache-control']).toBe('no-cache');

  const script = /<script[^>]+src="(\/assets\/[^"]+\.js)"/.exec(await deepLink.text())?.[1];
  expect(script).toBeDefined();
  const asset = await request.get(script ?? '');
  expect(asset.status()).toBe(200);
  expect(asset.headers()['cache-control']).toBe('public, max-age=31536000, immutable');
});

test('a bracket is drawn within the Content-Security-Policy', async ({ baseURL, page }) => {
  const violations: string[] = [];
  page.on('console', (message) => {
    if (message.text().includes('Content Security Policy')) violations.push(message.text());
  });
  // The image has no API: its answers come from here.
  await page.route(`${baseURL}/api/tournaments/7/details`, (route) =>
    route.fulfill({
      json: {
        data: {
          players: [],
          rankings: [ranking()],
          stages: [stage(1, true, [bracket()])],
          standings: {},
          teams,
          tournament: tournament(),
        },
      } satisfies OpenApi.TournamentDetailsResponse,
    }),
  );

  await page.goto('/tournaments/7/dashboard/bracket');
  await expect(page.locator('.participant.team-link').first()).toBeVisible();
  expect(violations).toEqual([]);
});
