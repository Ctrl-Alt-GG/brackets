import { describe, expect, it } from 'vitest';

import { matchWinner } from './matches';
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
