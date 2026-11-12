import { describe, expect, it } from 'vitest';

import type * as OpenApi from '../openapi';
import { roundLabel, toBracketViewerData } from './bracket-adapter';

type Match = OpenApi.MatchWithDetailsDefinitive;

function match(id: number, overrides: Partial<Match> = {}) {
  return {
    id,
    played: false,
    stage_item_input1_id: null,
    stage_item_input1_score: 0,
    stage_item_input1_winner_from_match_id: null,
    stage_item_input2_id: null,
    stage_item_input2_score: 0,
    stage_item_input2_winner_from_match_id: null,
    ...overrides,
  } as Match;
}

function stageItem(
  rounds: Match[][],
  type: OpenApi.StageItemWithRounds['type'] = 'SINGLE_ELIMINATION',
) {
  return {
    id: 1,
    inputs: [1, 2, 3, 4].map((id) => ({
      id,
      team: { name: `Team ${id}` },
      team_id: id + 100,
    })),
    name: 'Playoffs',
    rounds: rounds.map((matches, index) => ({ id: index + 1, matches })),
    team_count: 4,
    type,
  } as unknown as OpenApi.StageItemWithRounds;
}

describe('toBracketViewerData', () => {
  it('draws nothing before the matches exist', () => {
    expect(toBracketViewerData(stageItem([]), new Map(), 7)).toBeNull();
  });

  it('keeps real teams whose names equal the placeholder label', () => {
    const item = stageItem([[match(1, { stage_item_input1_id: 1, stage_item_input2_id: 2 })]]);
    const first = item.inputs[0];
    if ('team' in first) first.team.name = 'TBD';
    const data = toBracketViewerData(item, new Map(), 7);

    expect(data?.participants.find((participant) => participant.id === 1)?.name).toBe('TBD');
    expect(data?.matches[0].opponent1?.id).toBe(1);
  });

  it('lists the teams, and leaves an undecided competitor open', () => {
    const final = match(3, {
      stage_item_input1_id: 1,
      stage_item_input1_winner_from_match_id: 1,
      stage_item_input2_winner_from_match_id: 2,
    });
    const semiFinals = [
      match(1, {
        played: true,
        stage_item_input1_id: 1,
        stage_item_input1_score: 2,
        stage_item_input2_id: 2,
        stage_item_input2_score: 1,
      }),
      match(2, { stage_item_input1_id: 3, stage_item_input2_id: 4 }),
    ];

    const data = toBracketViewerData(stageItem([semiFinals, [final]]), new Map(), 7);

    expect(data?.participants.map((participant) => participant.name)).toEqual([
      'Team 1',
      'Team 2',
      'Team 3',
      'Team 4',
    ]);
    expect(data?.matches.map(({ id, round_id, status }) => [id, round_id, status])).toEqual([
      // Completed, ready to play, and waiting for the other semi-final.
      [1, 1, 4],
      [2, 1, 2],
      [3, 2, 1],
    ]);
    expect(data?.matches[0].opponent1).toEqual({ id: 1, result: 'win', score: 2 });
    expect(data?.matches[0].opponent2).toEqual({ id: 2, result: 'loss', score: 1 });
    // No score is shown for a match without a result: 0-0 would read as one.
    expect(data?.matches[1].opponent1).toEqual({ id: 3 });
    expect(data?.matches[2].opponent2).toEqual({ id: null });
  });

  it('orders every round by where its competitors come from, so the connectors line up', () => {
    const quarterFinals = [match(11), match(12), match(13), match(14)];
    const semiFinals = [
      // Stored first, but fed by the lower half of the bracket.
      match(21, {
        stage_item_input1_winner_from_match_id: 13,
        stage_item_input2_winner_from_match_id: 14,
      }),
      match(22, {
        stage_item_input1_winner_from_match_id: 11,
        stage_item_input2_winner_from_match_id: 12,
      }),
    ];

    const data = toBracketViewerData(stageItem([quarterFinals, semiFinals]), new Map(), 7);

    expect(data?.matches.filter((entry) => entry.round_id === 2).map((entry) => entry.id)).toEqual([
      22, 21,
    ]);
  });

  it('draws a Swiss stage item as a group, which has no connectors', () => {
    const data = toBracketViewerData(stageItem([[match(1)]], 'SWISS'), new Map(), 7);

    expect(data?.stages[0].type).toBe('round_robin');
  });
});

function knockout(roundNumber: number, roundCount: number) {
  return roundLabel({ groupType: 'single-bracket', roundCount, roundNumber });
}

describe('roundLabel', () => {
  it('names knockout rounds by how far they are from the final', () => {
    expect(knockout(4, 4)).toBe('Final');
    expect(knockout(3, 4)).toBe('Semi-finals');
    expect(knockout(2, 4)).toBe('Quarter-finals');
    expect(knockout(1, 4)).toBe('Round of 16');
    expect(knockout(1, 5)).toBe('Round of 32');
  });

  it('numbers the rounds of a Swiss stage item', () => {
    expect(roundLabel({ groupType: 'round-robin', roundCount: 5, roundNumber: 3 })).toBe('Round 3');
  });
});
