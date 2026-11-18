import { describe, expect, it } from 'vitest';

import type * as OpenApi from '../openapi';
import { at, entry, HOUR, match, START, tournament, type Match } from './test-fixtures';
import {
  isInProgress,
  isStageHappeningNow,
  matchStatus,
  nextMatch,
  tournamentPhase,
} from './tournament-rules';

describe('matchStatus', () => {
  it('is scheduled until the match starts', () => {
    expect(matchStatus(match(), at(-1))).toBe('scheduled');
    expect(matchStatus(match({ start_time: null }), at(0))).toBe('scheduled');
  });

  it('is live during the planned time', () => {
    expect(matchStatus(match(), at(0))).toBe('live');
    expect(matchStatus(match(), at(29 * 60_000))).toBe('live');
  });

  it('keeps waiting for the result of a match that ran over, instead of rescheduling it', () => {
    const status = matchStatus(match(), at(3 * HOUR));

    expect(status).toBe('awaiting');
    expect(isInProgress(status)).toBe(true);
  });

  it('is finished once it has a result, whenever that is entered', () => {
    expect(matchStatus(match({ played: true }), at(-HOUR))).toBe('finished');
  });

  it('waits for teams while a competitor is undecided, even past its planned time', () => {
    const winnerOfGroup = { winner_from_stage_item_id: 3, winner_position: 1 };

    expect(matchStatus(match({ stage_item_input2: null }), at(HOUR))).toBe('waiting');
    expect(
      matchStatus(
        match({ stage_item_input1: winnerOfGroup as Match['stage_item_input1'] }),
        at(HOUR),
      ),
    ).toBe('waiting');
  });
});

describe('nextMatch', () => {
  it('prefers the match in progress to an earlier one without teams', () => {
    const waiting = entry({ id: 1, stage_item_input1: null, start_time: '2000-01-01T10:00:00Z' });
    const running = entry({ id: 2, start_time: '2000-01-01T11:00:00Z' });

    expect(nextMatch([waiting, running])).toBe(running);
  });

  it('is the earliest match without a result otherwise', () => {
    const played = entry({ id: 1, played: true });
    const upcoming = entry({ id: 2, start_time: '2999-01-01T10:00:00Z' });

    expect(nextMatch([played, upcoming])).toBe(upcoming);
    expect(nextMatch([played])).toBeNull();
  });
});

describe('tournamentPhase', () => {
  it('is upcoming before the start', () => {
    expect(tournamentPhase(tournament(), at(-1))).toBe('upcoming');
  });

  it('is running while matches are left, or none have been drawn yet', () => {
    const halfway = tournament({ matches_played: 3, matches_total: 6 });

    expect(tournamentPhase(tournament(), at(HOUR))).toBe('running');
    expect(tournamentPhase(halfway, at(30 * 24 * HOUR))).toBe('running');
  });

  it('stays running for a while after the last result, when another round can still follow', () => {
    const done = tournament({
      last_match_end: '2026-06-06T16:00:00Z',
      matches_played: 6,
      matches_total: 6,
    });

    expect(tournamentPhase(done, at(5 * HOUR))).toBe('running');
    expect(tournamentPhase(done, at(8 * HOUR))).toBe('finished');
  });

  it('is finished once it is archived', () => {
    expect(tournamentPhase(tournament({ status: 'ARCHIVED' }), at(-HOUR))).toBe('finished');
  });

  it('stays running while a Swiss stage can still get rounds, also overnight', () => {
    const betweenSwissRounds = tournament({
      last_match_end: '2026-06-06T16:00:00Z',
      matches_played: 6,
      matches_total: 6,
      more_rounds_possible: true,
    });

    expect(tournamentPhase(betweenSwissRounds, at(20 * HOUR))).toBe('running');
  });
});

function swissStage(roundCreated: string, played: boolean) {
  return {
    is_active: true,
    stage_items: [
      {
        rounds: [{ created: roundCreated, is_draft: false, matches: [{ played }] }],
        type: 'SWISS',
      },
    ],
  } as unknown as OpenApi.StageWithStageItems;
}

describe('isStageHappeningNow', () => {
  it('is happening while matches are waiting for a result', () => {
    expect(isStageHappeningNow(swissStage(START, false), tournament(), at(30 * HOUR))).toBe(true);
  });

  it('lasts a while after the latest Swiss round, which the next one follows', () => {
    const done = swissStage(START, true);

    expect(isStageHappeningNow(done, tournament(), at(HOUR))).toBe(true);
    expect(isStageHappeningNow(done, tournament(), at(30 * HOUR))).toBe(false);
  });
});
