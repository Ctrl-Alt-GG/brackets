import { getI18n } from 'react-i18next';
import { describe, expect, it } from 'vitest';

import { matchWinner, roundName, stageItemName, stageName } from './matches';
import { match } from './test-fixtures';

describe('matchWinner', () => {
  it('has no winner without a result', () => {
    expect(matchWinner(match({ stage_item_input1_score: 0 }))).toBeNull();
  });

  it('tells a goalless draw from a match that was not played', () => {
    expect(matchWinner(match({ played: true }))).toBe('draw');
  });

  it('names the side with the higher score', () => {
    const played = { played: true, stage_item_input1_score: 1, stage_item_input2_score: 3 };

    expect(matchWinner(match(played))).toBe(2);
  });
});

describe('the names the site gives', () => {
  const english = getI18n().getFixedT('en');
  const hungarian = getI18n().getFixedT('hu');

  it('are shown in the language of the page', () => {
    expect(roundName({ name: 'Round 03' }, hungarian)).toBe('3. forduló');
    expect(roundName({ name: 'Round 03' }, english)).toBe('Round 03');
    expect(stageName({ name: 'Stage' }, hungarian)).toBe('Szakasz');
    expect(stageItemName({ name: 'Round Robin', type: 'ROUND_ROBIN' }, hungarian)).toBe(
      'Körmérkőzés',
    );
    expect(stageItemName({ name: 'Swiss', type: 'SWISS' }, english)).toBe('Swiss');
  });

  it('leave the names organizers gave as they are', () => {
    expect(roundName({ name: 'Döntő' }, english)).toBe('Döntő');
    expect(stageName({ name: 'Csoportkör' }, english)).toBe('Csoportkör');
    expect(stageItemName({ name: 'Upper bracket', type: 'SINGLE_ELIMINATION' }, hungarian)).toBe(
      'Upper bracket',
    );
    // Only the default of the stage item's own format counts.
    expect(stageItemName({ name: 'Swiss', type: 'ROUND_ROBIN' }, hungarian)).toBe('Swiss');
  });
});
