import { expect, test } from '@playwright/test';

import {
  bracket,
  player,
  sharedPlayer,
  sharedTeam,
  sharedTeams,
  signIn,
  stage,
  teams,
  tournamentApi,
} from './fixtures';

test('teams of the shared pool are added to a tournament', async ({ page }) => {
  await signIn(page.context());
  const { writes } = await tournamentApi(page, {
    pool: {
      players: [],
      teams: [...sharedTeams(teams), sharedTeam(5, 'Echo'), sharedTeam(6, 'Foxtrot')],
    },
  });
  await page.goto('/tournaments/7/teams');
  const add = page.getByRole('button', { name: 'Add selected teams' });
  await expect(add).toBeVisible();
  // The teams that take part already are not offered again.
  await expect(page.getByRole('checkbox', { name: 'Alpha' })).toHaveCount(0);

  await add.click();
  await expect(page.getByText('Pick at least one team.')).toBeVisible();
  await page.getByRole('checkbox', { name: 'Foxtrot' }).check();
  await add.click();

  await expect
    .poll(() => writes)
    .toEqual([{ body: { team_ids: [6] }, method: 'POST', path: '/api/tournaments/7/teams' }]);
  await expect(page.getByText('Teams added.')).toBeVisible();
});

test('a new team keeps members who do not play, and shows where its players play', async ({
  page,
}) => {
  await signIn(page.context());
  const ben = sharedPlayer(2, 'Ben');
  const { writes } = await tournamentApi(page, {
    pool: {
      players: [sharedPlayer(1, 'Ann'), ben],
      teams: [sharedTeam(2, 'Bravo', { members: [{ active: true, player: ben }] })],
    },
  });
  await page.goto('/roster');
  const create = page.getByRole('button', { name: 'Create team' });
  const form = page.locator('form').filter({ has: create });
  await form.getByLabel('Team name').fill('Echo');
  await expect(form.getByText('plays for Bravo')).toBeVisible();

  await form.getByRole('checkbox', { name: 'Ben' }).check();
  await form.getByRole('checkbox', { name: 'Inactive' }).check();
  await form.getByRole('checkbox', { name: 'Ann' }).check();
  await create.click();

  await expect
    .poll(() => writes)
    .toEqual([
      {
        body: {
          members: [
            { active: true, player_id: 1 },
            { active: false, player_id: 2 },
          ],
          name: 'Echo',
        },
        method: 'POST',
        path: '/api/teams',
      },
    ]);
  await expect(page.getByText('Team created.')).toBeVisible();
});

test('the schedule names who would have to be in two places at once', async ({ page }) => {
  await signIn(page.context());
  await tournamentApi(page, {
    conflicts: [
      {
        match_id: 1,
        other_match_id: 91,
        other_tournament_id: 8,
        other_tournament_name: 'Winter Cup',
        player_ids: [11],
        team_id: 1,
      },
      {
        match_id: 2,
        other_match_id: 92,
        other_tournament_id: 8,
        other_tournament_name: 'Winter Cup',
        player_ids: [],
        team_id: 3,
      },
    ],
    players: [player(11, 'Ann', 1)],
    stages: [stage(1, true, [bracket()])],
  });
  await page.goto('/tournaments/7/schedule');

  await expect(
    page.getByText('Some teams or players would have to be in two places at once.'),
  ).toBeVisible();
  await expect(page.getByText('Ann of Alpha plays in Winter Cup at this time too.')).toBeVisible();
  await expect(page.getByText('Charlie plays in Winter Cup at this time too.')).toBeVisible();
});
