import { expect, test } from '@playwright/test';

import type * as OpenApi from '../../src/openapi';
import { bracket, signIn, stage, tournamentApi, user } from './fixtures';

/** A round robin group, which gives the tournament a Standings page next to its Bracket. */
const group = {
  ...bracket(2),
  name: 'Group',
  rounds: [],
  type: 'ROUND_ROBIN',
  type_name: 'Round robin',
} satisfies OpenApi.StageItemWithRounds;

const exitBigScreen = { name: 'Exit big screen' } as const;

for (const opener of ['Schedule', 'Standings', 'Bracket']) {
  test(`a big screen opened from ${opener} returns there`, async ({ page }) => {
    await tournamentApi(page, { stages: [stage(1, true, [group, bracket()])] });
    await page.goto('/tournaments/summer-cup/dashboard');
    await page.getByRole('link', { name: opener, exact: true }).click();
    await page.getByRole('link', { name: 'Big screen' }).click();
    await expect(page).toHaveURL(/\/dashboard\/present\//);

    await page.getByRole('button', exitBigScreen).click();
    await expect(page).toHaveURL(new RegExp(`/dashboard/${opener.toLowerCase()}$`));
    // Leaving went back, so the big screen isn't in the history between the two pages.
    await page.goBack();
    await expect(page).toHaveURL(/\/dashboard$/);
  });
}

test('an organizer leaves a big screen for the workspace page that opened it', async ({ page }) => {
  await signIn(page.context());
  await tournamentApi(page, { stages: [stage(1, true, [bracket()])] });

  await page.goto('/tournaments/7/schedule');
  await page.getByRole('link', { name: 'Big screen' }).click();
  await expect(page).toHaveURL(/\/tournaments\/summer-cup\/dashboard\/present\/schedule$/);

  await page.getByRole('button', exitBigScreen).click();
  await expect(page).toHaveURL(/\/tournaments\/7\/schedule$/);
});

test('a big screen opened from a bookmark exits to the page that shows the same', async ({
  page,
}) => {
  const { state } = await tournamentApi(page, { stages: [stage(1, true, [group, bracket()])] });

  await page.goto('/tournaments/summer-cup/dashboard/present/standings');
  await page.getByRole('button', exitBigScreen).click();
  await expect(page).toHaveURL(/\/dashboard\/standings$/);

  // Without groups, the standings are the bracket.
  state.stages = [stage(1, true, [bracket()])];
  await page.goto('/tournaments/summer-cup/dashboard/present/standings');
  await page.getByRole('button', exitBigScreen).click();
  await expect(page).toHaveURL(/\/dashboard\/bracket$/);

  await page.goto('/tournaments/summer-cup/dashboard/present/schedule');
  await page.getByRole('button', exitBigScreen).click();
  await expect(page).toHaveURL(/\/dashboard\/schedule$/);
});

test('the exit of a big screen fades out while nobody uses the screen', async ({ page }) => {
  await page.clock.install();
  await tournamentApi(page);
  await page.goto('/tournaments/summer-cup/dashboard/present/schedule');
  const exit = page.getByRole('button', exitBigScreen);
  await expect(exit).toHaveCSS('opacity', '1');

  await page.clock.runFor(3_500);
  await expect(exit).toHaveCSS('opacity', '0');

  await page.mouse.move(200, 200);
  await expect(exit).toHaveCSS('opacity', '1');
  await page.clock.runFor(3_500);
  await expect(exit).toHaveCSS('opacity', '0');

  // A keyboard user who moves to it sees it.
  await page.keyboard.press('Tab');
  await expect(exit).toBeFocused();
  await expect(exit).toHaveCSS('opacity', '1');
});

test('organizers switch between the two views of the page they are on', async ({ page }) => {
  await signIn(page.context());
  await tournamentApi(page, { stages: [stage(1, true, [group])] });

  await page.goto('/tournaments/7/schedule');
  await page.getByRole('link', { name: 'Public view' }).click();
  await expect(page).toHaveURL(/\/tournaments\/summer-cup\/dashboard\/schedule$/);

  await page.getByRole('link', { name: 'Standings', exact: true }).click();
  await page.getByRole('link', { name: 'Organizer view' }).click();
  await expect(page).toHaveURL(/\/tournaments\/7\/rankings$/);

  await page.getByRole('link', { name: 'Settings', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Tournament settings' })).toBeVisible();
  await page.getByRole('link', { name: 'Public view' }).click();
  await expect(page).toHaveURL(/\/tournaments\/summer-cup\/dashboard$/);
});

test('a team picked before logging in stays in the organizer view', async ({ page }) => {
  await tournamentApi(page, { stages: [stage(1, true, [bracket()])] }, (write) =>
    write.path === '/api/token'
      ? {
          json: {
            access_token: '',
            name: 'Owner',
            token_type: 'bearer',
            user_id: 1,
          } satisfies OpenApi.Token,
        }
      : undefined,
  );
  await page.goto('/tournaments/summer-cup/dashboard');
  await page.getByRole('combobox', { name: 'Your team' }).selectOption({ label: 'Bravo' });

  await page.getByRole('link', { name: 'Organizer login' }).click();
  await page.getByLabel('Email').fill(user.email);
  await page.getByLabel('Password').fill('correct-horse-battery-staple');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.getByRole('link', { name: 'Organizer view' }).click();

  await expect(page).toHaveURL(/\/tournaments\/7$/);
  await expect(page.getByText('Your team', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Bravo' })).toBeVisible();
  // The team is picked and changed on the public view.
  await expect(page.getByRole('button', { name: 'Change team' })).toHaveCount(0);
});

test('organizers who picked no team are not asked for one in the organizer view', async ({
  page,
}) => {
  await signIn(page.context());
  await tournamentApi(page, { stages: [stage(1, true, [bracket()])] });

  await page.goto('/tournaments/7');
  await expect(page.getByRole('heading', { name: 'Coming up next' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Find your team' })).toHaveCount(0);
  await expect(page.getByText('Your team', { exact: true })).toHaveCount(0);
});
