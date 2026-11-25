import { expect, test, type Page } from '@playwright/test';

import type * as OpenApi from '../../src/openapi';
import {
  deferred,
  inputs,
  match,
  refresh,
  round,
  signIn,
  stage,
  tournament,
  tournamentApi,
  user,
} from './fixtures';

const initialUser = { ...user, name: 'Initial name' } satisfies OpenApi.UserPublic;

async function profileApi(page: Page) {
  const state = {
    user: { ...initialUser },
    submitted: [] as Record<string, unknown>[],
    delaySave: null as Promise<void> | null,
  };
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/users/me') return route.fulfill({ json: { data: state.user } });
    if (path === '/api/users/1' && request.method() === 'PUT') {
      const body = request.postDataJSON();
      state.submitted.push(body);
      await state.delaySave;
      state.user = { ...state.user, email: body.email, name: body.name };
      return route.fulfill({
        json: { data: state.user } satisfies OpenApi.UserPublicResponse,
      });
    }
    if (path === '/api/tournaments') return route.fulfill({ json: { data: [] } });
    return route.fulfill({ status: 404, json: { detail: `Unexpected request: ${path}` } });
  });
  return state;
}

test('a saved profile follows remote updates and does not write an old name back', async ({
  page,
}) => {
  await signIn(page.context());
  const state = await profileApi(page);
  await page.goto('/user');
  await page.getByLabel('Display name').fill('First saved name');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect(page.getByText('Account saved.', { exact: true })).toBeVisible();
  state.user.name = 'Remote name';
  await refresh(page);
  await expect(page.getByLabel('Display name')).toHaveValue('Remote name');
  await page.getByLabel('Email', { exact: true }).fill('new@example.org');
  await page.getByLabel('Current password', { exact: true }).first().fill('a current password');
  await page.getByRole('button', { name: 'Save profile' }).click();
  await expect.poll(() => state.submitted.at(-1)?.email).toBe('new@example.org');
  expect(state.submitted.at(-1)?.name).toBe('Remote name');
});

for (const afterSubmit of ['Typed while saving', initialUser.name]) {
  test(`a save preserves a later edit to ${JSON.stringify(afterSubmit)}`, async ({ page }) => {
    await signIn(page.context());
    const state = await profileApi(page);
    const save = deferred();
    state.delaySave = save.promise;
    await page.goto('/user');
    await page.getByLabel('Display name').fill('Submitted name');
    await page.getByRole('button', { name: 'Save profile' }).click();
    await expect.poll(() => state.submitted.length).toBe(1);
    await page.getByLabel('Display name').fill(afterSubmit);
    save.release();
    await expect(page.getByText('Account saved.', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Display name')).toHaveValue(afterSubmit);
    state.user.name = 'Another remote name';
    await refresh(page);
    await expect(page.getByLabel('Display name')).toHaveValue(afterSubmit);
    await page.getByRole('button', { name: 'Save profile' }).click();
    await expect.poll(() => state.submitted.length).toBe(2);
    await expect(page.getByRole('button', { name: 'Save profile' })).toBeEnabled();
    state.user.name = 'Latest remote name';
    await refresh(page);
    await expect(page.getByLabel('Display name')).toHaveValue('Latest remote name');
  });
}

const liveTournament = tournament({ dashboard_endpoint: null, name: 'Live tournament' });

function details(name: string) {
  return {
    data: {
      players: [],
      rankings: [],
      stages: [],
      standings: {},
      teams: [],
      tournament: { ...liveTournament, name },
    },
  } satisfies OpenApi.TournamentDetailsResponse;
}

test('failed tournament refresh keeps data, warns with last update and recovers on retry', async ({
  page,
}) => {
  let fail = false;
  let name = liveTournament.name;
  await page.route('**/api/tournaments/7/details', (route) =>
    fail
      ? route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } })
      : route.fulfill({ json: details(name) }),
  );
  await page.goto('/tournaments/7/dashboard/schedule');
  await expect(page.getByRole('heading', { name: 'Live tournament' })).toBeVisible();
  fail = true;
  await refresh(page);
  await expect(
    page.getByText('Updates are unavailable. This view may be out of date.'),
  ).toBeVisible();
  await expect(page.getByText(/Last updated/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Live tournament' })).toBeVisible();
  fail = false;
  name = 'Recovered tournament';
  await page.getByRole('button', { name: 'Retry updates' }).click();
  await expect(
    page.getByText('Updates are unavailable. This view may be out of date.'),
  ).toBeHidden();
  await expect(page.getByRole('heading', { name })).toBeVisible();
});

test('going offline before refresh warns on paused updates and recovers online', async ({
  page,
}) => {
  let name = liveTournament.name;
  await page.route('**/api/tournaments/7/details', (route) =>
    route.fulfill({ json: details(name) }),
  );
  await page.goto('/tournaments/7/dashboard/schedule');
  await expect(page.getByRole('heading', { name: 'Live tournament' })).toBeVisible();
  await page.context().setOffline(true);
  await page.evaluate(async () => {
    window.dispatchEvent(new Event('offline'));
    const modulePath = '/src/app/query-client.ts';
    const { queryClient } = await import(/* @vite-ignore */ modulePath);
    // A paused refetch stays pending until the network returns.
    void queryClient.invalidateQueries();
  });
  await expect(
    page.getByText('Updates are unavailable. This view may be out of date.'),
  ).toBeVisible();
  await expect(page.getByText(/Last updated/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Live tournament' })).toBeVisible();
  name = 'Back online tournament';
  await page.context().setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(
    page.getByText('Updates are unavailable. This view may be out of date.'),
  ).toBeHidden();
  await expect(page.getByRole('heading', { name })).toBeVisible();
});

test('the shared teams and players load apart from having none', async ({ page }) => {
  await signIn(page.context());
  await profileApi(page);
  const loading = deferred();
  let fail = true;
  await page.route('**/api/teams', async (route) => {
    await loading.promise;
    return fail
      ? route.fulfill({ status: 503, json: { detail: 'Teams unavailable' } })
      : route.fulfill({ json: { data: [] } satisfies OpenApi.TeamsResponse });
  });
  await page.route('**/api/players', (route) =>
    route.fulfill({ json: { data: [] } satisfies OpenApi.PlayersResponse }),
  );
  await page.goto('/roster');
  await expect(page.getByText('Loading teams and players…')).toBeVisible();
  await expect(page.getByText('No teams yet.')).toBeHidden();
  loading.release();
  await expect(
    page.getByRole('heading', { name: 'Unable to load teams and players' }),
  ).toBeVisible();
  await expect(page.getByText('No teams yet.')).toBeHidden();
  fail = false;
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByText('No teams yet.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Create team' })).toBeVisible();
});

test('failed logout remains signed in and a successful retry ends the session', async ({
  page,
}) => {
  await signIn(page.context());
  await profileApi(page);
  let fail = true;
  await page.route('**/api/logout', (route) =>
    fail
      ? route.abort()
      : route.fulfill({
          status: 204,
          headers: {
            'Set-Cookie': 'bracket_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict',
          },
        }),
  );
  await page.goto('/user');
  await page.getByRole('button', { name: 'Log out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Log out failed' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Log out', exact: true })).toBeVisible();
  expect(
    await page.evaluate(() => JSON.parse(localStorage.getItem('bracket:session') ?? 'null')),
  ).not.toBeNull();
  expect((await page.context().cookies()).some((cookie) => cookie.name === 'bracket_session')).toBe(
    true,
  );
  fail = false;
  await page.getByRole('button', { name: 'Try logging out again' }).click();
  await expect(page.getByRole('heading', { name: 'Log out failed' })).toBeHidden();
  await expect(
    page.getByRole('link', { name: 'Organizer login', exact: true }).first(),
  ).toBeVisible();
  expect(
    await page.evaluate(() => JSON.parse(localStorage.getItem('bracket:session') ?? 'null')),
  ).toBeNull();
  expect((await page.context().cookies()).some((cookie) => cookie.name === 'bracket_session')).toBe(
    false,
  );
});

test('Swiss regeneration uses one atomic request and retains pairings after a failure', async ({
  page,
}) => {
  await signIn(page.context());
  const slots = inputs(3, [1, 2]);
  const swiss = (matchId: number) =>
    stage(1, true, [
      {
        created: liveTournament.created,
        id: 3,
        inputs: slots,
        name: 'Swiss group',
        ranking_id: 1,
        rounds: [
          round(5, 3, [match(matchId, 5, slots[0], slots[1])], {
            is_draft: true,
            name: 'Round 01',
          }),
        ],
        stage_id: 1,
        team_count: 2,
        type: 'SWISS',
        type_name: 'Swiss',
      },
    ]);
  let fail = true;
  const { state, writes } = await tournamentApi(
    page,
    { stages: [swiss(1)], tournament: liveTournament },
    (write) => {
      if (write.path !== '/api/tournaments/7/rounds/5/regenerate') {
        return { json: { detail: 'Unexpected destructive request' }, status: 500 };
      }
      if (fail) return { json: { detail: 'No replacement pairing is available' }, status: 400 };
      state.stages = [swiss(2)];
      return undefined;
    },
  );
  await page.goto('/tournaments/7/stages');
  const pairing = page.locator('li').filter({ hasText: 'Alpha' });
  const regenerate = async () => {
    await page.getByRole('button', { name: 'Regenerate pairings', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Regenerate pairings' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  };
  await expect(pairing).toContainText('Bravo');
  await regenerate();
  await expect(
    page.getByText('No replacement pairing is available', { exact: true }),
  ).toBeVisible();
  await expect(pairing).toContainText('Bravo');
  fail = false;
  await regenerate();
  await expect(page.getByText('New pairings generated.', { exact: true })).toBeVisible();
  expect(writes.map((write) => `${write.method} ${write.path}`)).toEqual([
    'POST /api/tournaments/7/rounds/5/regenerate',
    'POST /api/tournaments/7/rounds/5/regenerate',
  ]);
  await expect(pairing).toContainText('Bravo');
});
