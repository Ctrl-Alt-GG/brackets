import { expect, test, type BrowserContext, type Page, type Route } from '@playwright/test';

const ORIGIN = 'http://127.0.0.1:5188';
const CREATED = '2026-01-01T00:00:00Z';
const user = { id: 1, email: 'owner@example.org', name: 'Owner', created: CREATED };

function tournament(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    club_id: 1,
    name: 'Summer Cup',
    created: CREATED,
    start_time: '2030-06-01T10:00:00Z',
    duration_minutes: 30,
    margin_minutes: 5,
    dashboard_public: true,
    dashboard_endpoint: 'summer-cup',
    logo_path: null,
    players_can_be_in_multiple_teams: false,
    status: 'OPEN',
    matches_total: 0,
    matches_played: 0,
    last_match_end: null,
    more_rounds_possible: false,
    ...overrides,
  };
}

const teams = ['Alpha', 'Bravo', 'Charlie', 'Delta'].map((name, index) => ({
  id: index + 1,
  tournament_id: 7,
  name,
  active: true,
  players: [],
  logo_path: null,
  created: CREATED,
  elo_score: '1200',
  swiss_score: '0',
  wins: 0,
  draws: 0,
  losses: 0,
}));

function inputs(stageItemId: number, teamIds: number[]) {
  return teamIds.map((teamId, index) => ({
    id: stageItemId * 10 + index + 1,
    slot: index + 1,
    tournament_id: 7,
    stage_item_id: stageItemId,
    team_id: teamId,
    team: teams[teamId - 1],
    winner_from_stage_item_id: null,
    winner_position: null,
    points: '0',
    wins: 0,
    draws: 0,
    losses: 0,
  }));
}

/** A knockout of four teams: two semi-finals and a final that waits for their winners. */
function bracket(stageItemId = 3) {
  const slots = inputs(stageItemId, [1, 2, 3, 4]);
  const match = (id: number, roundId: number, input1: unknown, input2: unknown) => ({
    id,
    round_id: roundId,
    created: CREATED,
    start_time: '2030-06-01T10:00:00Z',
    duration_minutes: 30,
    margin_minutes: 5,
    custom_duration_minutes: null,
    custom_margin_minutes: null,
    stage_item_input1: input1,
    stage_item_input2: input2,
    stage_item_input1_id: (input1 as { id?: number } | null)?.id ?? null,
    stage_item_input2_id: (input2 as { id?: number } | null)?.id ?? null,
    stage_item_input1_winner_from_match_id: null,
    stage_item_input2_winner_from_match_id: null,
    stage_item_input1_score: 0,
    stage_item_input2_score: 0,
    stage_item_input1_conflict: false,
    stage_item_input2_conflict: false,
    scoreless_result: false,
    played: false,
  });
  return {
    id: stageItemId,
    stage_id: 1,
    name: 'Playoffs',
    type: 'SINGLE_ELIMINATION',
    type_name: 'Single elimination',
    team_count: 4,
    ranking_id: 1,
    created: CREATED,
    inputs: slots,
    rounds: [
      {
        id: 5,
        stage_item_id: stageItemId,
        name: 'Round 01',
        is_draft: false,
        created: CREATED,
        matches: [match(1, 5, slots[0], slots[1]), match(2, 5, slots[2], slots[3])],
      },
      {
        id: 6,
        stage_item_id: stageItemId,
        name: 'Round 02',
        is_draft: false,
        created: CREATED,
        matches: [
          {
            ...match(3, 6, null, null),
            stage_item_input1_winner_from_match_id: 1,
            stage_item_input2_winner_from_match_id: 2,
          },
        ],
      },
    ],
  };
}

function stage(id: number, isActive: boolean, stageItems: unknown[] = []) {
  return {
    id,
    name: `Stage ${id}`,
    created: CREATED,
    is_active: isActive,
    tournament_id: 7,
    custom_duration_minutes: null,
    stage_items: stageItems,
  };
}

const ranking = {
  id: 1,
  tournament_id: 7,
  created: CREATED,
  position: 0,
  win_points: '1',
  draw_points: '0.5',
  loss_points: '0',
  add_score_points: false,
};

async function signIn(context: BrowserContext, session = 'session') {
  await context.addInitScript(() => {
    localStorage.setItem('bracket:session', JSON.stringify({ name: 'Owner', user_id: 1 }));
  });
  await context.addCookies([
    { name: 'bracket_session', value: session, url: ORIGIN, httpOnly: true },
  ]);
}

type Api = {
  tournament?: ReturnType<typeof tournament>;
  stages?: unknown[];
  nextStageRankings?: Record<string, unknown>;
  tournaments?: unknown[];
};

/** The API of one tournament, for the workspace and the Details pages. Changes are recorded. */
async function tournamentApi(page: Page, api: Api = {}) {
  const writes: string[] = [];
  const data = {
    tournament: api.tournament ?? tournament(),
    stages: api.stages ?? [],
  };
  await page.route('**/api/**', async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') {
      writes.push(`${request.method()} ${path}`);
      return route.fulfill({ json: { success: true } });
    }
    const responses: Record<string, unknown> = {
      '/api/users/me': user,
      '/api/clubs': [],
      '/api/tournaments': api.tournaments ?? [{ ...data.tournament, can_manage: true }],
      '/api/tournaments/7': data.tournament,
      '/api/tournaments/7/access': { can_manage: false },
      '/api/tournaments/7/details': {
        players: [],
        rankings: [ranking],
        stages: data.stages,
        standings: {},
        teams,
        tournament: data.tournament,
      },
      '/api/tournaments/7/stages': data.stages,
      '/api/tournaments/7/players': { count: 0, players: [] },
      '/api/tournaments/7/teams': { count: teams.length, teams },
      '/api/tournaments/7/rankings': [ranking],
      '/api/tournaments/7/standings': {},
      '/api/tournaments/7/available_inputs': {},
      '/api/tournaments/7/next_stage_rankings': api.nextStageRankings ?? {},
    };
    return Object.hasOwn(responses, path)
      ? route.fulfill({ json: { data: responses[path] } })
      : route.fulfill({ status: 404, json: { detail: `Unexpected request: ${path}` } });
  });
  return writes;
}

test('a session that ended on another device leaves the tournaments visible', async ({
  browser,
}) => {
  // The server: which session cookies are still valid. A password change ends the others.
  const valid = new Set(['laptop', 'phone']);
  const loggedOut: string[] = [];
  const contexts = await Promise.all([1, 2].map(() => browser.newContext({ baseURL: ORIGIN })));
  await Promise.all(
    (['laptop', 'phone'] as const).map(async (session, index) => {
      const context = contexts[index];
      await signIn(context, session);
      await context.route('**/api/**', async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        const cookie = /bracket_session=([^;]+)/.exec(request.headers().cookie ?? '')?.[1] ?? '';
        if (path === '/api/users/1/password') {
          valid.delete('phone');
          return route.fulfill({ json: { success: true } });
        }
        if (path === '/api/logout') {
          loggedOut.push(cookie);
          return route.fulfill({
            status: 204,
            headers: {
              'Set-Cookie': 'bracket_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict',
            },
          });
        }
        // Anyone may see the public tournaments, with or without a valid session.
        if (path === '/api/tournaments') {
          return route.fulfill({ json: { data: [{ ...tournament(), can_manage: false }] } });
        }
        if (!valid.has(cookie)) {
          return route.fulfill({ status: 401, json: { detail: 'Could not validate credentials' } });
        }
        if (path === '/api/users/me') return route.fulfill({ json: { data: user } });
        if (path === '/api/clubs') return route.fulfill({ json: { data: [] } });
        return route.fulfill({ status: 404, json: { detail: path } });
      });
    }),
  );
  const [laptop, phone] = await Promise.all(contexts.map((context) => context.newPage()));

  await laptop.goto('/user');
  await laptop.getByLabel('Current password').fill('the old password');
  await laptop.getByLabel('New password', { exact: true }).fill('correct-horse-battery-staple');
  await laptop.getByLabel('Repeat the new password').fill('correct-horse-battery-staple');
  await laptop.getByRole('button', { name: 'Update password' }).click();
  await expect(laptop.getByText('Password updated.')).toBeVisible();

  await phone.goto('/');
  await expect(phone.getByRole('heading', { name: 'Summer Cup' })).toBeVisible();
  await expect(phone.getByRole('link', { name: 'Organizer login' })).toBeVisible();
  // The page can't remove the HttpOnly cookie itself: logging out does.
  await expect.poll(() => loggedOut).toEqual(['phone']);
  expect((await contexts[1].cookies()).some((cookie) => cookie.name === 'bracket_session')).toBe(
    false,
  );
  await Promise.all(contexts.map((context) => context.close()));
});

test('a new password is typed twice, and a mismatch is never sent', async ({ page }) => {
  await signIn(page.context());
  const writes = await tournamentApi(page);
  await page.goto('/user');
  await page.getByLabel('Current password').fill('the old password');
  await page.getByLabel('New password', { exact: true }).fill('correct-horse-battery-staple');
  await page.getByLabel('Repeat the new password').fill('correct-horse-battery-stapel');
  await page.getByRole('button', { name: 'Update password' }).click();

  await expect(page.getByText("The two new passwords aren't the same")).toBeVisible();
  await page.getByLabel('Show the passwords').check();
  await expect(page.getByLabel('Repeat the new password')).toHaveAttribute('type', 'text');
  expect(writes).toEqual([]);
});

test('the Details link is shown in full, copied, and drawn as a QR code', async ({
  context,
  page,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: ORIGIN });
  await signIn(context);
  await tournamentApi(page);
  const link = `${ORIGIN}/tournaments/summer-cup/dashboard`;

  await page.goto('/tournaments/7/settings');
  await expect(page.getByRole('link', { name: link })).toBeVisible();
  await expect(page.getByRole('img', { name: `QR code of ${link}` })).toBeVisible();
  await page.getByRole('button', { name: 'Copy link' }).click();

  await expect(page.getByText('Link copied.')).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(link);
});

test('archiving asks first, and says when players lose the tournament', async ({ page }) => {
  await signIn(page.context());
  const writes = await tournamentApi(page, {
    tournament: tournament({ dashboard_endpoint: null, dashboard_public: false }),
  });
  await page.goto('/tournaments/7/settings');
  const archive = page.getByRole('button', { name: 'Archive tournament' });

  await archive.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Players can no longer see it');
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toBeHidden();
  expect(writes).toEqual([]);

  await archive.click();
  await page.getByRole('dialog').getByRole('button', { name: 'Archive tournament' }).click();
  await expect.poll(() => writes).toEqual(['POST /api/tournaments/7/change-status']);
});

test('visitors who open a workspace page land on its Details page', async ({ page }) => {
  await tournamentApi(page);

  await page.goto('/tournaments/7/teams');
  await expect(page).toHaveURL(/\/tournaments\/7\/dashboard\/teams$/);
  await expect(page.getByRole('heading', { name: 'Teams', exact: true })).toBeVisible();

  await page.goto('/tournaments/7/stages');
  await expect(page).toHaveURL(/\/tournaments\/7\/dashboard\/standings$/);
});

test('stage activation offers only the directions there are', async ({ page }) => {
  await signIn(page.context());
  const next = page.getByRole('button', { name: 'Activate next stage' });
  const previous = page.getByRole('button', { name: 'Activate previous stage' });

  await tournamentApi(page, { stages: [stage(1, false), stage(2, false)] });
  await page.goto('/tournaments/7/stages');
  await expect(next).toBeEnabled();
  await expect(previous).toBeDisabled();

  await page.unrouteAll();
  await tournamentApi(page, { stages: [stage(1, false), stage(2, true)] });
  await page.reload();
  await expect(next).toBeDisabled();
  await expect(previous).toBeEnabled();
});

test('activating the next stage names the places only seeding decided', async ({ page }) => {
  await signIn(page.context());
  const group = { ...bracket(3), name: 'Group', type: 'ROUND_ROBIN', type_name: 'Round robin' };
  const writes = await tournamentApi(page, {
    nextStageRankings: {
      '4': [
        {
          stage_item_input: {
            id: 41,
            slot: 1,
            tournament_id: 7,
            stage_item_id: 4,
            team_id: null,
            winner_from_stage_item_id: 3,
            winner_position: 1,
            points: '0',
            wins: 0,
            draws: 0,
            losses: 0,
          },
          team: teams[1],
          tied_team: teams[2],
        },
      ],
    },
    stages: [stage(1, true, [{ ...group, rounds: [] }]), stage(2, false)],
  });
  await page.goto('/tournaments/7/stages');
  await page.getByRole('button', { name: 'Activate next stage' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText(
    'Bravo and Charlie are level on every criterion: only seeding puts Bravo ahead.',
  );
  await dialog.getByRole('button', { name: 'Activate next stage' }).click();
  await expect.poll(() => writes).toEqual(['POST /api/tournaments/7/stages/activate']);
});

test('a knockout lists its slots by the first-round match they form', async ({ page }) => {
  await signIn(page.context());
  await tournamentApi(page, { stages: [stage(1, true, [bracket()])] });
  await page.goto('/tournaments/7/stages');
  // Every slot is filled, so the list starts folded.
  await page.locator('summary').filter({ hasText: '4 of 4 slots filled' }).click();

  const firstMatch = page.getByRole('group', { name: 'Match 1 of the first round' });
  await expect(firstMatch.getByRole('combobox')).toHaveCount(2);
  await expect(firstMatch.getByLabel('Slot 1')).toBeVisible();
  await expect(firstMatch.getByLabel('Slot 2')).toBeVisible();
});

test('a new knockout takes the bracket size nearest to the team count', async ({ page }) => {
  await signIn(page.context());
  await tournamentApi(page, { stages: [stage(1, true)] });
  await page.goto('/tournaments/7/stages');

  await page.getByLabel('Team count').fill('6');
  await page.getByLabel('Type').selectOption('SINGLE_ELIMINATION');

  await expect(page.getByLabel('Team count')).toHaveValue('4');
});

test('team names in a bracket on the big screen are not links', async ({ page }) => {
  await tournamentApi(page, { stages: [stage(1, true, [bracket()])] });

  await page.goto('/tournaments/7/dashboard/bracket');
  await expect(page.locator('.participant.team-link').first()).toBeVisible();

  await page.goto('/tournaments/7/dashboard/present/standings');
  await expect(page.locator('.participant').first()).toBeVisible();
  await expect(page.locator('.participant.team-link')).toHaveCount(0);
});

test('organizers see their own tournaments and the other public ones', async ({ page }) => {
  await signIn(page.context());
  await tournamentApi(page);
  let fail = true;
  // Registered last, so it answers before the general mock.
  await page.route(
    (url) => url.pathname === '/api/tournaments',
    (route) =>
      fail
        ? route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } })
        : route.fulfill({
            json: {
              data: [
                { ...tournament(), can_manage: true },
                {
                  ...tournament({ id: 8, name: 'Other Cup', dashboard_endpoint: null }),
                  can_manage: false,
                },
              ],
            },
          }),
  );
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Unable to load tournaments' })).toBeVisible();

  fail = false;
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByRole('heading', { name: 'Your tournaments' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Other tournaments' })).toBeVisible();
  const other = page.locator('article').filter({ hasText: 'Other Cup' });
  await expect(other.getByRole('link', { name: 'Details' })).toBeVisible();
  await expect(other.getByRole('link', { name: 'Manage' })).toHaveCount(0);
});

test('visitors can read the tournament pages in Hungarian', async ({ page }) => {
  await tournamentApi(page, { tournaments: [{ ...tournament(), can_manage: false }] });
  await page.goto('/');
  await page.getByLabel('Language').selectOption('hu');

  await expect(page.getByRole('heading', { name: 'Versenyek', level: 1 })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'hu');
  await page.reload();
  await expect(page.getByRole('link', { name: 'Részletek' })).toBeVisible();

  await page.goto('/tournaments/7/dashboard');
  await expect(page.getByRole('heading', { name: 'Keresd meg a csapatodat' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Áttekintés' })).toBeVisible();
});
