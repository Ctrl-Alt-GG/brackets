import { expect, test, type Page } from '@playwright/test';

import type * as OpenApi from '../../src/openapi';
import {
  bracket,
  deferred,
  ORIGIN,
  signIn,
  stage,
  teams,
  tournament,
  tournamentApi,
  user,
  type Write,
} from './fixtures';

function storedSession(page: Page) {
  return page.evaluate(() => JSON.parse(localStorage.getItem('bracket:session') ?? 'null'));
}

function logouts(writes: Write[]) {
  return writes.filter((write) => write.path === '/api/logout');
}

async function logIn(page: Page, password: string) {
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Log in' }).click();
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

test('a wrong password typed while signed in keeps the session', async ({ page }) => {
  await signIn(page.context());
  const { writes } = await tournamentApi(page, {}, (write) =>
    write.path === '/api/token'
      ? { json: { detail: 'Incorrect email or password' }, status: 401 }
      : undefined,
  );
  await page.goto('/login');
  await logIn(page, 'not the password');

  await expect(page.getByText('Incorrect email or password')).toBeVisible();
  expect(logouts(writes)).toEqual([]);
  expect(await storedSession(page)).toMatchObject({ user_id: 1 });
});

test('a refusal for an earlier session does not end the session after it', async ({ page }) => {
  await signIn(page.context(), 'ended');
  const { writes } = await tournamentApi(page, {}, (write) =>
    write.path === '/api/token'
      ? {
          json: {
            access_token: 'new',
            name: 'Owner',
            token_type: 'bearer',
            user_id: 1,
          } satisfies OpenApi.Token,
        }
      : undefined,
  );
  // The ended session's question of who is signed in is answered after the next login.
  const lateAnswer = deferred();
  let ended = true;
  await page.route('**/api/users/me', async (route) => {
    if (!ended) return route.fallback();
    ended = false;
    await lateAnswer.promise;
    return route.fulfill({ json: { detail: 'Could not validate credentials' }, status: 401 });
  });
  await page.goto('/login');
  await logIn(page, 'correct-horse-battery-staple');
  await expect(page.getByText('Logged in successfully.')).toBeVisible();

  const refused = page.waitForResponse((response) => response.status() === 401);
  lateAnswer.release();
  await refused;
  await page.evaluate(() => new Promise((resolve) => setTimeout(resolve)));

  expect(logouts(writes)).toEqual([]);
  expect(await storedSession(page)).toMatchObject({ user_id: 1 });
  await expect(page.getByText('Your session expired. Please log in again.')).toBeHidden();
});

test('a new password is typed twice, and a mismatch is never sent', async ({ page }) => {
  await signIn(page.context());
  const { writes } = await tournamentApi(page);
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
  const { writes } = await tournamentApi(page, {
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
  await expect
    .poll(() => writes)
    .toEqual([
      { body: { status: 'ARCHIVED' }, method: 'POST', path: '/api/tournaments/7/change-status' },
    ]);
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

  const { state } = await tournamentApi(page, { stages: [stage(1, false), stage(2, false)] });
  await page.goto('/tournaments/7/stages');
  await expect(next).toBeEnabled();
  await expect(previous).toBeDisabled();

  state.stages = [stage(1, false), stage(2, true)];
  await page.reload();
  await expect(next).toBeDisabled();
  await expect(previous).toBeEnabled();
});

test('activating the next stage names the places only seeding decided', async ({ page }) => {
  await signIn(page.context());
  const group = {
    ...bracket(3),
    name: 'Group',
    type: 'ROUND_ROBIN',
    type_name: 'Round robin',
  } as const;
  const { writes } = await tournamentApi(page, {
    nextStageRankings: {
      '4': [
        {
          stage_item_input: {
            draws: 0,
            id: 41,
            losses: 0,
            points: '0',
            slot: 1,
            stage_item_id: 4,
            team_id: null,
            tournament_id: 7,
            winner_from_stage_item_id: 3,
            winner_position: 1,
            wins: 0,
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
  await expect
    .poll(() => writes)
    .toEqual([
      {
        body: { direction: 'next', discard_results: false },
        method: 'POST',
        path: '/api/tournaments/7/stages/activate',
      },
    ]);
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
