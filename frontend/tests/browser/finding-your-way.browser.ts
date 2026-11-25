import { expect, test, type Page } from '@playwright/test';

import type * as OpenApi from '../../src/openapi';
import { bracket, inputs, match, round, signIn, stage, team, tournamentApi } from './fixtures';

const slots = inputs(4, [1, 2, 3, 4]);

/** A group of four whose second round starts after the first. */
const group = {
  ...bracket(4),
  inputs: slots,
  name: 'Group A',
  rounds: [
    round(41, 4, [match(11, 41, slots[0], slots[1]), match(12, 41, slots[2], slots[3])], {
      name: 'Round 01',
    }),
    round(
      42,
      4,
      [
        match(13, 42, slots[0], slots[2], { start_time: '2030-06-01T10:35:00Z' }),
        match(14, 42, slots[1], slots[3], { start_time: '2030-06-01T10:35:00Z' }),
      ],
      { name: 'Round 02' },
    ),
  ],
  team_count: 4,
  type: 'ROUND_ROBIN',
  type_name: 'Round robin',
} satisfies OpenApi.StageItemWithRounds;

const standings = {
  '4': slots.map(
    (slot) =>
      ({
        draws: 0,
        losses: 0,
        points: '0',
        score_against: 0,
        score_for: 0,
        stage_item_input_id: slot.id,
        wins: 0,
      }) satisfies OpenApi.StageItemInputStanding,
  ),
};

/** A group stage that is being played, and a knockout after it. */
const stages = [stage(1, true, [group]), stage(2, false, [bracket(3)])];

const onPhone = (page: Page) => page.setViewportSize({ height: 844, width: 390 });

test('a new tournament shows its organizers the steps to get it ready', async ({ page }) => {
  await signIn(page.context());
  const { state } = await tournamentApi(page, { stages: [], teams: [] });
  await page.goto('/tournaments/7');

  await expect(page.getByRole('heading', { name: 'Get the tournament ready' })).toBeVisible();
  const checklist = page.getByRole('list').filter({ hasText: 'Add the teams that take part' });
  await expect(checklist.getByRole('listitem')).toHaveText([
    /Add the teams that take part/,
    /Set up the stages/,
    /Share the Details link/,
  ]);
  await expect(page.getByRole('heading', { name: 'Coming up next' })).toHaveCount(0);
  await checklist.getByRole('link', { name: 'Teams' }).click();
  await expect(page).toHaveURL(/\/tournaments\/7\/teams$/);

  // Teams take part now: that step is done, and setting up the stages is next.
  state.teams = [team(1, 'Alpha'), team(2, 'Bravo')];
  await page.goto('/tournaments/7');
  await expect(checklist.getByRole('listitem').first()).toContainText('Done');
  await expect(checklist.getByRole('link', { name: 'Teams' })).toHaveCount(0);
  await expect(checklist.getByRole('link', { name: 'Stages' })).toBeVisible();
});

test('the overview shows the matches that start next, and links to the rest', async ({ page }) => {
  await tournamentApi(page, { stages });
  await page.goto('/tournaments/summer-cup/dashboard');

  await expect(page.getByText('Group A · Round 01')).toHaveCount(2);
  await expect(page.getByText('Group A · Round 02')).toHaveCount(0);
  await page.getByRole('link', { name: 'Full schedule' }).click();
  await expect(page).toHaveURL(/\/tournaments\/summer-cup\/dashboard\/schedule$/);
  await expect(page.getByText('Group A · Round 02')).toHaveCount(2);
});

test('organizers open a group or a bracket from the overview without leaving their view', async ({
  page,
}) => {
  await signIn(page.context());
  await tournamentApi(page, { stages, standings });
  await page.goto('/tournaments/7');

  await page.getByRole('link', { name: /Group A/ }).click();
  await expect(page).toHaveURL(/\/tournaments\/7\/rankings#stage-item-4$/);
  await expect(page.getByRole('heading', { name: 'Group A' })).toBeVisible();

  await page.goBack();
  await page.getByRole('link', { name: /Playoffs/ }).click();
  await expect(page).toHaveURL(/\/tournaments\/7\/stages#stage-item-3$/);
  // The knockout's stage hasn't started, but the link opens it.
  await expect(page.locator('#stage-item-3')).toBeVisible();
});

test('on a phone, every page of a tournament has its tab in sight', async ({ page }) => {
  await onPhone(page);
  await tournamentApi(page, { stages });
  await page.goto('/tournaments/summer-cup/dashboard');
  const pages = page.getByRole('navigation', { name: 'Tournament pages' }).getByRole('link');
  await expect(pages).toHaveText(['Overview', 'Schedule', 'Standings', 'Bracket', 'Teams']);
  await Promise.all((await pages.all()).map((tab) => expect(tab).toBeInViewport()));

  await signIn(page.context());
  await page.goto('/tournaments/7');
  await expect(pages).toHaveCount(7);
  await Promise.all((await pages.all()).map((tab) => expect(tab).toBeInViewport()));
});

test('on a phone, the standings show the points without scrolling sideways', async ({ page }) => {
  await onPhone(page);
  await tournamentApi(page, { stages, standings });
  await page.goto('/tournaments/summer-cup/dashboard/standings');

  await expect(page.getByRole('columnheader', { name: 'Points' })).toBeInViewport({ ratio: 1 });
});

test('the login page does not link to itself', async ({ page }) => {
  await tournamentApi(page);
  await page.goto('/login');

  await expect(page.getByRole('heading', { name: 'Organizer login' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Organizer login' })).toHaveCount(0);
});

test('points rules are counted from one, and the existing ones come first', async ({ page }) => {
  await signIn(page.context());
  await tournamentApi(page, { stages, standings });
  await page.goto('/tournaments/7/rankings');

  const headings = page.getByRole('heading', { level: 2 });
  await expect(headings).toHaveText(['Standings', 'Points rules', 'New points rule']);
  await expect(page.getByText('Points rule 1', { exact: true })).toBeVisible();
});
