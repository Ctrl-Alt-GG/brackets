import { describe, expect, it } from 'vitest';

import type * as OpenApi from '../openapi';
import type { FlattenedMatch } from './types';
import {
  getErrorMessage,
  groupBy,
  isInProgress,
  loginPath,
  matchStatus,
  matchWinner,
  nextMatch,
  publicTournamentPath,
  safeNextPath,
  teamLogoUrl,
  tournamentLogoUrl,
  tournamentPhase,
} from './utils';

const START = '2026-06-06T12:00:00Z';
const HOUR = 60 * 60 * 1000;

function at(offsetMs: number) {
  return new Date(START).getTime() + offsetMs;
}

// The wider of the two match types: a competitor can be undecided.
type Match = OpenApi.MatchWithDetails;

function match(overrides: Partial<Match> = {}) {
  return {
    duration_minutes: 30,
    id: 1,
    played: false,
    stage_item_input1: { team: { name: 'Home' }, team_id: 1 },
    stage_item_input1_score: 0,
    stage_item_input2: { team: { name: 'Away' }, team_id: 2 },
    stage_item_input2_score: 0,
    start_time: START,
    ...overrides,
  } as Match;
}

function entry(overrides: Partial<Match>) {
  return { match: match(overrides) } as FlattenedMatch;
}

function response(status: number, data: unknown, headers: Record<string, string> = {}) {
  return {
    message: `Request failed with status code ${status}`,
    response: { data, headers, status },
  };
}

function tournament(overrides: Partial<OpenApi.Tournament> = {}) {
  return {
    dashboard_endpoint: null,
    dashboard_public: false,
    id: 7,
    last_match_end: null,
    logo_path: null,
    matches_played: 0,
    matches_total: 0,
    start_time: START,
    status: 'OPEN',
    ...overrides,
  } as OpenApi.Tournament;
}

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
});

describe('loginPath and safeNextPath', () => {
  it('brings the organizer back to the page they came from', () => {
    expect(loginPath('/tournaments/3/stages')).toBe('/login?next=%2Ftournaments%2F3%2Fstages');
  });

  it('has nowhere to return to from the home page or the account pages', () => {
    expect(loginPath('/')).toBe('/login');
    expect(loginPath('/login')).toBe('/login');
    expect(loginPath('/create-account')).toBe('/login');
  });

  it('only follows a path on this site', () => {
    expect(safeNextPath('/tournaments/3/stages')).toBe('/tournaments/3/stages');
    expect(safeNextPath(null)).toBe('/');
    expect(safeNextPath('https://evil.example/')).toBe('/');
    expect(safeNextPath('//evil.example/')).toBe('/');
    expect(safeNextPath('/\\evil.example/')).toBe('/');
    expect(safeNextPath('javascript:alert(1)')).toBe('/');
  });
});

describe('getErrorMessage', () => {
  it("shows the API's own message", () => {
    expect(getErrorMessage(response(400, { detail: 'A knockout match needs a winner.' }))).toBe(
      'A knockout match needs a winner.',
    );
  });

  it('shows a validation message without where it came from', () => {
    const detail = [{ loc: ['body', 'names'], msg: 'Value error, Enter at least one name' }];

    expect(getErrorMessage(response(422, { detail }))).toBe('Enter at least one name');
  });

  it('says when to try again after too many attempts', () => {
    const body = { error: 'Rate limit exceeded' };

    expect(getErrorMessage(response(429, body, { 'retry-after': '45' }))).toBe(
      'Too many attempts. Try again in a minute.',
    );
    expect(getErrorMessage(response(429, body, { 'retry-after': '700' }))).toBe(
      'Too many attempts. Try again in 12 minutes.',
    );
    expect(getErrorMessage(response(429, body))).toBe(
      'Too many attempts. Try again in a few minutes.',
    );
  });

  it('falls back to the error itself, then to a general message', () => {
    expect(getErrorMessage(new Error('Network Error'))).toBe('Network Error');
    expect(getErrorMessage(null)).toBe('The request failed. Check your connection and try again.');
  });
});

describe('groupBy', () => {
  it('keeps the groups and their items in the order they appear', () => {
    const groups = groupBy(['b1', 'a1', 'b2', 'c1', 'a2'], (item) => item[0]);

    expect([...groups]).toEqual([
      ['b', ['b1', 'b2']],
      ['a', ['a1', 'a2']],
      ['c', ['c1']],
    ]);
  });
});

describe('links', () => {
  it('uses the Details link only while the Details page is on', () => {
    const named = { dashboard_endpoint: ' summer-cup ' };

    expect(publicTournamentPath(tournament({ ...named, dashboard_public: true }))).toBe(
      '/tournaments/summer-cup/dashboard',
    );
    expect(publicTournamentPath(tournament(named))).toBe('/tournaments/7/dashboard');
    expect(publicTournamentPath(tournament({ dashboard_public: true }))).toBe(
      '/tournaments/7/dashboard',
    );
  });

  it('has no logo address without a logo', () => {
    expect(tournamentLogoUrl(tournament())).toBeNull();
    expect(teamLogoUrl({ id: 4, logo_path: null, tournament_id: 7 })).toBeNull();
  });

  it('changes the logo address with every upload, so browsers fetch the new picture', () => {
    expect(tournamentLogoUrl(tournament({ logo_path: 'a b.png' }))).toBe(
      '/api/tournaments/7/logo?v=a%20b.png',
    );
    expect(teamLogoUrl({ id: 4, logo_path: 'new.jpg', tournament_id: 7 })).toBe(
      '/api/tournaments/7/teams/4/logo?v=new.jpg',
    );
  });
});
