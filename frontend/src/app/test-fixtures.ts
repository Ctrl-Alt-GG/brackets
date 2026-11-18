/* Records for unit tests, with the fields the tested code reads. */

import type * as OpenApi from '../openapi';
import type { FlattenedMatch } from './types';

export const START = '2026-06-06T12:00:00Z';
export const HOUR = 60 * 60 * 1000;

/** A time relative to `START`, in milliseconds. */
export function at(offsetMs: number) {
  return new Date(START).getTime() + offsetMs;
}

// The wider of the two match types: a competitor can be undecided.
export type Match = OpenApi.MatchWithDetails;

export function match(overrides: Partial<Match> = {}) {
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

export function entry(overrides: Partial<Match>) {
  return { match: match(overrides) } as FlattenedMatch;
}

export function tournament(overrides: Partial<OpenApi.Tournament> = {}) {
  return {
    dashboard_endpoint: null,
    dashboard_public: false,
    id: 7,
    last_match_end: null,
    logo_path: null,
    matches_played: 0,
    matches_total: 0,
    more_rounds_possible: false,
    start_time: START,
    status: 'OPEN',
    ...overrides,
  } as OpenApi.Tournament;
}
