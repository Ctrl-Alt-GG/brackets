import { expect, test } from '@playwright/test';

import {
  deferred,
  ranking,
  refresh,
  sharedPlayer,
  sharedTeams,
  signIn,
  team,
  tournamentApi,
} from './fixtures';

const STALE = 'Updates are unavailable. This view may be out of date.';

test('an untouched ranking field follows the server, also when another field is saved', async ({
  page,
}) => {
  await signIn(page.context());
  const points = { draw_points: '1', loss_points: '0' };
  const { state, writes } = await tournamentApi(page, {
    rankings: [ranking({ ...points, win_points: '3' })],
  });
  await page.goto('/tournaments/7/rankings');
  const editor = page.locator('details').filter({ hasText: 'Points rule 1' });
  await editor.locator('summary').click();
  await expect(editor.getByLabel('Win points')).toHaveValue('3');

  // Another organizer changes the points: the API sends decimals as text.
  state.rankings = [ranking({ ...points, win_points: '5' })];
  await refresh(page);
  await expect(editor.getByLabel('Win points')).toHaveValue('5');

  await editor.getByLabel('Add raw score points').check();
  await editor.getByRole('button', { name: 'Save rule' }).click();
  await expect
    .poll(() => writes.at(-1)?.body)
    .toEqual({
      add_score_points: true,
      draw_points: 1,
      loss_points: 0,
      position: 0,
      win_points: 5,
    });

  // The server answers with its own notation of the saved values, which still counts as saved.
  state.rankings = [
    ranking({
      add_score_points: true,
      draw_points: '1.000000',
      loss_points: '0',
      win_points: '5.000000',
    }),
  ];
  await refresh(page);
  state.rankings = [ranking({ add_score_points: true, ...points, win_points: '6' })];
  await refresh(page);
  await expect(editor.getByLabel('Win points')).toHaveValue('6');
});

test('a new ranking is locked while it is saved, then empty for the next one', async ({ page }) => {
  await signIn(page.context());
  const save = deferred();
  const { writes } = await tournamentApi(page, {}, async () => {
    await save.promise;
    return undefined;
  });
  await page.goto('/tournaments/7/rankings');
  const form = page
    .locator('form')
    .filter({ has: page.getByRole('button', { name: 'Create rule' }) });

  await form.getByLabel('Win points').fill('7');
  await form.getByRole('button', { name: 'Create rule' }).click();
  await expect.poll(() => writes.length).toBe(1);
  // Nothing typed now could survive the form emptying once the ranking is saved.
  await expect(form.getByLabel('Win points')).toBeDisabled();

  save.release();
  await expect(page.getByText('Points rule created.')).toBeVisible();
  await expect(form.getByLabel('Win points')).toBeEnabled();
  await expect(form.getByLabel('Win points')).toHaveValue('3');
  expect(writes[0]).toEqual({
    body: { add_score_points: false, draw_points: 1, loss_points: 0, win_points: 7 },
    method: 'POST',
    path: '/api/tournaments/7/rankings',
  });
});

test('a save is done once the server has it, and a failed refresh after it says so', async ({
  page,
}) => {
  await signIn(page.context());
  await tournamentApi(page, { rankings: [ranking({ win_points: '3' })] });
  await page.goto('/tournaments/7/rankings');
  const editor = page.locator('details').filter({ hasText: 'Points rule 1' });
  await editor.locator('summary').click();

  // The refresh after the save waits, and then fails.
  const refreshAnswer = deferred();
  await page.route('**/api/tournaments/7/workspace', async (route) => {
    await refreshAnswer.promise;
    await route.fulfill({ json: { detail: 'Temporarily unavailable' }, status: 503 });
  });
  await editor.getByLabel('Win points').fill('4');
  await editor.getByRole('button', { name: 'Save rule' }).click();

  await expect(page.getByText('Points rule saved.')).toBeVisible();
  await expect(editor.getByRole('button', { name: 'Save rule' })).toBeEnabled();
  await expect(page.getByText(STALE)).toBeHidden();

  refreshAnswer.release();
  await expect(page.getByText(STALE)).toBeVisible();
  await expect(editor.getByLabel('Win points')).toHaveValue('4');
});

test('leaving a tournament before it has loaded cancels its request', async ({ page }) => {
  await tournamentApi(page);
  const answer = deferred();
  await page.route('**/api/tournaments/7/details', async (route) => {
    await answer.promise;
    await route.fallback().catch(() => undefined);
  });
  const cancelled: string[] = [];
  page.on('requestfailed', (request) => {
    if (new URL(request.url()).pathname === '/api/tournaments/7/details') {
      cancelled.push(request.failure()?.errorText ?? '');
    }
  });

  await page.goto('/tournaments/7/dashboard');
  await expect(page.getByText('Loading tournament…')).toBeVisible();
  await page.getByRole('link', { name: 'Ctrl-Alt-GG Bracket' }).click();

  await expect.poll(() => cancelled).toEqual(['net::ERR_ABORTED']);
  answer.release();
});

test('a closed team editor makes its player list when it is first opened', async ({ page }) => {
  await signIn(page.context());
  const tournamentTeams = [team(1, 'Alpha'), team(2, 'Bravo')];
  await tournamentApi(page, {
    pool: {
      players: [sharedPlayer(1, 'Ann'), sharedPlayer(2, 'Ben')],
      teams: sharedTeams(tournamentTeams),
    },
    teams: tournamentTeams,
  });
  await page.goto('/tournaments/7/teams');
  // The shared players have loaded, but no editor is open to list them.
  await expect(page.getByText('Every team takes part already.')).toBeVisible();
  const ann = page.getByRole('checkbox', { name: 'Ann' });
  await expect(ann).toHaveCount(0);

  const alpha = page.locator('details').filter({ hasText: 'Alpha' });
  await alpha.locator('summary').click();
  await expect(ann).toHaveCount(1);
  await ann.check();

  // Closed again, the editor keeps what was changed in it.
  await alpha.locator('summary').click();
  await alpha.locator('summary').click();
  await expect(ann).toBeChecked();
});
