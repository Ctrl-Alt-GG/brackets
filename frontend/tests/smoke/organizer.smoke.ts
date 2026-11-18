import { expect, test, type Page } from '@playwright/test';

import type * as OpenApi from '../../src/openapi';
import { ORGANIZER } from './organizer';

/** The API as the signed-in organizer, with the session cookie that logging in set. */
async function call<T>(page: Page, method: 'GET' | 'POST' | 'PUT', path: string, data?: unknown) {
  const response = await page.request.fetch(`/api${path}`, {
    data,
    // Changes signed in with the cookie need this header (CSRF protection).
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    method,
  });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as T;
}

async function workspace(page: Page, tournamentId: number) {
  const response = await call<OpenApi.TournamentWorkspaceResponse>(
    page,
    'GET',
    `/tournaments/${tournamentId}/workspace`,
  );
  return response.data;
}

/** A tournament of two teams in a round robin, which is being played. */
async function seedTournament(page: Page) {
  // Event names are unique per organizer, and the database outlives a run.
  const { data: club } = await call<OpenApi.ClubResponse>(page, 'POST', '/clubs', {
    name: `Smoke test event ${Date.now()}`,
  } satisfies OpenApi.ClubCreateBody);
  if (!club) throw new Error('The API created no event.');
  const { data: tournament } = await call<OpenApi.TournamentResponse>(
    page,
    'POST',
    '/tournaments',
    {
      club_id: club.id,
      dashboard_public: true,
      duration_minutes: 20,
      margin_minutes: 5,
      name: 'Smoke Cup',
      players_can_be_in_multiple_teams: false,
      start_time: new Date().toISOString(),
    } satisfies OpenApi.TournamentBody,
  );
  const path = `/tournaments/${tournament.id}`;
  const teams = await Promise.all(
    ['Red', 'Blue'].map(async (name) => {
      const team = await call<OpenApi.SingleTeamResponse>(page, 'POST', `${path}/teams`, {
        active: true,
        name,
        player_ids: [],
      } satisfies OpenApi.TeamBody);
      return team.data;
    }),
  );

  await call(page, 'POST', `${path}/stages`);
  const { rankings, stages } = await workspace(page, tournament.id);
  await call(page, 'POST', `${path}/stage_items`, {
    name: 'Group',
    ranking_id: rankings[0].id,
    stage_id: stages[0].id,
    team_count: 2,
    type: 'ROUND_ROBIN',
  } satisfies OpenApi.StageItemCreateBody);
  const [stageItem] = (await workspace(page, tournament.id)).stages[0].stage_items;
  await Promise.all(
    stageItem.inputs.map((input, index) =>
      call(page, 'PUT', `${path}/stage_items/${stageItem.id}/inputs/${input.id}`, {
        team_id: teams[index].id,
      } satisfies OpenApi.StageItemInputUpdateBodyFinal),
    ),
  );
  await call(page, 'POST', `${path}/stages/activate`, {
    direction: 'next',
  } satisfies OpenApi.StageActivateBody);
  return tournament.id;
}

test('an organizer logs in, edits a ranking, enters a score and logs out', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill(ORGANIZER.email);
  await page.getByLabel('Password').fill(ORGANIZER.password);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByText('Logged in successfully.')).toBeVisible();
  const cookies = await page.context().cookies();
  expect(cookies.find((cookie) => cookie.name === 'bracket_session')?.httpOnly).toBe(true);

  const tournamentId = await seedTournament(page);

  // The API keeps points as decimals, and sends them back in its own notation.
  await page.goto(`/tournaments/${tournamentId}/rankings`);
  const ranking = page.locator('details').filter({ hasText: 'Ranking #0' });
  await ranking.locator('summary').click();
  await ranking.getByLabel('Win points').fill('3');
  await ranking.getByRole('button', { name: 'Save ranking' }).click();
  await expect(page.getByText('Ranking saved.')).toBeVisible();
  await expect(ranking.locator('summary')).toContainText('Win 3 · Draw 0.5 · Loss 0');
  await page.reload();
  await ranking.locator('summary').click();
  await expect(ranking.getByLabel('Win points')).toHaveValue('3');
  await expect(ranking.getByLabel('Draw points')).toHaveValue('0.5');

  // The refresh after the score is saved shows the match as played.
  await page.goto(`/tournaments/${tournamentId}/schedule`);
  await expect(page.getByText('0 of 1 matches played')).toBeVisible();
  await page.getByLabel('Red score').fill('2');
  await page.getByLabel('Blue score').fill('1');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Score saved: Red vs Blue.')).toBeVisible();
  await expect(page.getByText('1 of 1 matches played')).toBeVisible();

  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page.getByText('Logged out successfully.')).toBeVisible();
  expect((await page.context().cookies()).some((cookie) => cookie.name === 'bracket_session')).toBe(
    false,
  );
  expect((await page.request.get('/api/users/me')).status()).toBe(401);
});
