import { expect, test, type Page } from '@playwright/test';

type User = { id: number; email: string; name: string; created: string };
const initialUser: User = {
  id: 1,
  email: 'owner@example.org',
  name: 'Initial name',
  created: '2026-01-01T00:00:00Z',
};

async function signedIn(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('bracket:session', JSON.stringify({ name: 'Initial name', user_id: 1 }));
  });
}

async function refresh(page: Page) {
  await page.evaluate(async () => {
    // Exercise the same refetch path as polling, without waiting a minute between assertions.
    const modulePath = '/src/app/query-client.ts';
    const { queryClient } = await import(/* @vite-ignore */ modulePath);
    await queryClient.invalidateQueries();
  });
}

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
      return route.fulfill({ json: { data: state.user } });
    }
    if (path === '/api/tournaments') return route.fulfill({ json: { data: [] } });
    if (path === '/api/clubs') return route.fulfill({ json: { data: [] } });
    return route.fulfill({ status: 404, json: { detail: `Unexpected request: ${path}` } });
  });
  return state;
}

test('a saved profile follows remote updates and does not write an old name back', async ({
  page,
}) => {
  await signedIn(page);
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
    await signedIn(page);
    const state = await profileApi(page);
    let release!: () => void;
    state.delaySave = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.goto('/user');
    await page.getByLabel('Display name').fill('Submitted name');
    await page.getByRole('button', { name: 'Save profile' }).click();
    await expect.poll(() => state.submitted.length).toBe(1);
    await page.getByLabel('Display name').fill(afterSubmit);
    release();
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

const tournament = {
  id: 7,
  club_id: 1,
  name: 'Live tournament',
  created: '2026-01-01T00:00:00Z',
  start_time: '2030-06-01T10:00:00Z',
  duration_minutes: 30,
  margin_minutes: 5,
  dashboard_public: true,
  dashboard_endpoint: null,
  logo_path: null,
  players_can_be_in_multiple_teams: false,
  status: 'OPEN',
  matches_total: 0,
  matches_played: 0,
  last_match_end: null,
};

test('failed tournament refresh keeps data, warns with last update and recovers on retry', async ({
  page,
}) => {
  let fail = false;
  let name = tournament.name;
  await page.route('**/api/tournaments/7/details', (route) =>
    fail
      ? route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } })
      : route.fulfill({
          json: {
            data: {
              tournament: { ...tournament, name },
              players: [],
              teams: [],
              rankings: [],
              stages: [],
              standings: {},
            },
          },
        }),
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
  let name = tournament.name;
  await page.route('**/api/tournaments/7/details', (route) =>
    route.fulfill({
      json: {
        data: {
          tournament: { ...tournament, name },
          players: [],
          teams: [],
          rankings: [],
          stages: [],
          standings: {},
        },
      },
    }),
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

test('event loading and failures are distinct from having no events', async ({ page }) => {
  await signedIn(page);
  await profileApi(page);
  let finishLoading!: () => void;
  const waiting = new Promise<void>((resolve) => {
    finishLoading = resolve;
  });
  let fail = true;
  await page.route('**/api/clubs', async (route) => {
    await waiting;
    return fail
      ? route.fulfill({ status: 503, json: { detail: 'Events unavailable' } })
      : route.fulfill({
          json: { data: [{ id: 1, name: 'My event', created: initialUser.created }] },
        });
  });
  await page.goto('/');
  await expect(page.getByText('Loading events…')).toBeVisible();
  await expect(
    page.getByText('You need an event before you can create a tournament.'),
  ).toBeHidden();
  finishLoading();
  await expect(page.getByRole('heading', { name: 'Unable to load events' })).toBeVisible();
  await expect(
    page.getByText('You need an event before you can create a tournament.'),
  ).toBeHidden();
  fail = false;
  await page.getByRole('button', { name: 'Retry loading events' }).click();
  await expect(page.getByRole('button', { name: 'Create tournament', exact: true })).toBeVisible();
});

test('failed logout remains signed in and a successful retry ends the session', async ({
  page,
}) => {
  await signedIn(page);
  await profileApi(page);
  await page
    .context()
    .addCookies([
      { name: 'bracket_session', value: 'session', url: 'http://127.0.0.1:5188', httpOnly: true },
    ]);
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
  await signedIn(page);
  const teams = ['Alpha', 'Bravo'].map((name, index) => ({
    id: index + 1,
    tournament_id: 7,
    name,
    active: true,
    players: [],
    logo_path: null,
  }));
  const inputs = teams.map((team, index) => ({
    id: index + 11,
    stage_item_id: 3,
    tournament_id: 7,
    slot: index + 1,
    team_id: team.id,
    team,
    winner_from_stage_item_id: null,
    winner_position: null,
    wins: 0,
    draws: 0,
    losses: 0,
    points: '1200',
  }));
  const writes: string[] = [];
  let fail = true;
  let matchId = 1;
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/users/me') return route.fulfill({ json: { data: initialUser } });
    if (request.method() !== 'GET') {
      writes.push(`${request.method()} ${path}`);
      if (path.endsWith('/rounds/5/regenerate')) {
        if (fail)
          return route.fulfill({
            status: 400,
            json: { detail: 'No replacement pairing is available' },
          });
        matchId += 1;
        return route.fulfill({ json: { success: true } });
      }
      return route.fulfill({ status: 500, json: { detail: 'Unexpected destructive request' } });
    }
    const endpoint = path.replace('/api/tournaments/7', '');
    const data: Record<string, unknown> = {
      '': tournament,
      '/stages': [
        {
          id: 1,
          name: 'Swiss stage',
          is_active: true,
          tournament_id: 7,
          custom_duration_minutes: null,
          stage_items: [
            {
              id: 3,
              stage_id: 1,
              name: 'Swiss group',
              type: 'SWISS',
              type_name: 'Swiss',
              team_count: 2,
              ranking_id: 1,
              inputs,
              rounds: [
                {
                  id: 5,
                  stage_item_id: 3,
                  name: 'Round 01',
                  is_draft: true,
                  matches: [
                    {
                      id: matchId,
                      round_id: 5,
                      stage_item_input1: inputs[0],
                      stage_item_input2: inputs[1],
                      stage_item_input1_id: 11,
                      stage_item_input2_id: 12,
                      played: false,
                      stage_item_input1_score: 0,
                      stage_item_input2_score: 0,
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
      '/players': { count: 0, players: [] },
      '/teams': { count: teams.length, teams },
      '/rankings': [
        {
          id: 1,
          position: 0,
          win_points: '3',
          draw_points: '1',
          loss_points: '0',
          add_score_points: false,
        },
      ],
      '/standings': {},
      '/available_inputs': {},
      '/next_stage_rankings': {},
    };
    return Object.hasOwn(data, endpoint)
      ? route.fulfill({ json: { data: data[endpoint] } })
      : route.fulfill({ status: 404, json: { detail: path } });
  });
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto('/tournaments/7/stages');
  const pairing = page.locator('li').filter({ hasText: 'Alpha' });
  await expect(pairing).toContainText('Bravo');
  await page.getByRole('button', { name: 'Regenerate pairings', exact: true }).click();
  await expect(
    page.getByText('No replacement pairing is available', { exact: true }),
  ).toBeVisible();
  await expect(pairing).toContainText('Bravo');
  fail = false;
  await page.getByRole('button', { name: 'Regenerate pairings', exact: true }).click();
  await expect(page.getByText('New pairings generated.', { exact: true })).toBeVisible();
  expect(writes).toEqual([
    'POST /api/tournaments/7/rounds/5/regenerate',
    'POST /api/tournaments/7/rounds/5/regenerate',
  ]);
  await expect(pairing).toContainText('Bravo');
});
