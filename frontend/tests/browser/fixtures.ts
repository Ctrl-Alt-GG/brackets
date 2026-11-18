/* Records and a mocked API for the browser tests. The records are checked against the API's
   generated types, so they keep the shape the backend answers with. */

import type { BrowserContext, Page, Route } from '@playwright/test';

import type * as OpenApi from '../../src/openapi';

export const ORIGIN = 'http://127.0.0.1:5188';
export const CREATED = '2026-01-01T00:00:00Z';

export const user = {
  account_type: 'REGULAR',
  created: CREATED,
  email: 'owner@example.org',
  id: 1,
  name: 'Owner',
} satisfies OpenApi.UserPublic;

export function tournament(overrides: Partial<OpenApi.Tournament> = {}) {
  return {
    club_id: 1,
    created: CREATED,
    dashboard_endpoint: 'summer-cup',
    dashboard_public: true,
    duration_minutes: 30,
    id: 7,
    last_match_end: null,
    logo_path: null,
    margin_minutes: 5,
    matches_played: 0,
    matches_total: 0,
    more_rounds_possible: false,
    name: 'Summer Cup',
    players_can_be_in_multiple_teams: false,
    start_time: '2030-06-01T10:00:00Z',
    status: 'OPEN',
    ...overrides,
  } satisfies OpenApi.Tournament;
}

export function team(id: number, name: string) {
  return {
    active: true,
    created: CREATED,
    draws: 0,
    elo_score: '1200',
    id,
    logo_path: null,
    losses: 0,
    name,
    players: [],
    swiss_score: '0',
    tournament_id: 7,
    wins: 0,
  } satisfies OpenApi.FullTeamWithPlayers;
}

export function player(id: number, name: string) {
  return {
    active: true,
    created: CREATED,
    draws: 0,
    elo_score: '1200',
    id,
    losses: 0,
    name,
    swiss_score: '0',
    tournament_id: 7,
    wins: 0,
  } satisfies OpenApi.Player;
}

export const teams = ['Alpha', 'Bravo', 'Charlie', 'Delta'].map((name, index) =>
  team(index + 1, name),
);

export function inputs(stageItemId: number, teamIds: number[]) {
  return teamIds.map(
    (teamId, index) =>
      ({
        draws: 0,
        id: stageItemId * 10 + index + 1,
        losses: 0,
        points: '0',
        slot: index + 1,
        stage_item_id: stageItemId,
        team: teams[teamId - 1],
        team_id: teamId,
        tournament_id: 7,
        winner_from_stage_item_id: null,
        winner_position: null,
        wins: 0,
      }) satisfies OpenApi.StageItemInputFinal,
  );
}

export function match(
  id: number,
  roundId: number,
  input1: OpenApi.StageItemInputFinal | null,
  input2: OpenApi.StageItemInputFinal | null,
  overrides: Partial<OpenApi.MatchWithDetails> = {},
) {
  return {
    created: CREATED,
    custom_duration_minutes: null,
    custom_margin_minutes: null,
    duration_minutes: 30,
    id,
    margin_minutes: 5,
    played: false,
    round_id: roundId,
    scoreless_result: false,
    stage_item_input1: input1,
    stage_item_input1_conflict: false,
    stage_item_input1_id: input1?.id ?? null,
    stage_item_input1_score: 0,
    stage_item_input1_winner_from_match_id: null,
    stage_item_input2: input2,
    stage_item_input2_conflict: false,
    stage_item_input2_id: input2?.id ?? null,
    stage_item_input2_score: 0,
    stage_item_input2_winner_from_match_id: null,
    start_time: '2030-06-01T10:00:00Z',
    ...overrides,
  } satisfies OpenApi.MatchWithDetails;
}

export function round(
  id: number,
  stageItemId: number,
  matches: OpenApi.MatchWithDetails[],
  overrides: Partial<OpenApi.RoundWithMatches> = {},
) {
  return {
    created: CREATED,
    id,
    is_draft: false,
    matches,
    name: `Round 0${id}`,
    stage_item_id: stageItemId,
    ...overrides,
  } satisfies OpenApi.RoundWithMatches;
}

/** A knockout of four teams: two semi-finals and a final that waits for their winners. */
export function bracket(stageItemId = 3) {
  const slots = inputs(stageItemId, [1, 2, 3, 4]);
  return {
    created: CREATED,
    id: stageItemId,
    inputs: slots,
    name: 'Playoffs',
    ranking_id: 1,
    rounds: [
      round(5, stageItemId, [match(1, 5, slots[0], slots[1]), match(2, 5, slots[2], slots[3])], {
        name: 'Round 01',
      }),
      round(
        6,
        stageItemId,
        [
          match(3, 6, null, null, {
            stage_item_input1_winner_from_match_id: 1,
            stage_item_input2_winner_from_match_id: 2,
          }),
        ],
        { name: 'Round 02' },
      ),
    ],
    stage_id: 1,
    team_count: 4,
    type: 'SINGLE_ELIMINATION',
    type_name: 'Single elimination',
  } satisfies OpenApi.StageItemWithRounds;
}

export function stage(
  id: number,
  isActive: boolean,
  stageItems: OpenApi.StageItemWithRounds[] = [],
) {
  return {
    created: CREATED,
    custom_duration_minutes: null,
    id,
    is_active: isActive,
    name: `Stage ${id}`,
    stage_items: stageItems,
    tournament_id: 7,
  } satisfies OpenApi.StageWithStageItems;
}

export function ranking(overrides: Partial<OpenApi.Ranking> = {}) {
  return {
    add_score_points: false,
    created: CREATED,
    draw_points: '0.5',
    id: 1,
    loss_points: '0',
    position: 0,
    tournament_id: 7,
    win_points: '1',
    ...overrides,
  } satisfies OpenApi.Ranking;
}

/** What the mocked API answers with. Tests change it to make the server's data change. */
export type ApiState = {
  canManage: boolean;
  nextStageRankings: OpenApi.TournamentWorkspace['next_stage_rankings'];
  players: OpenApi.Player[];
  rankings: OpenApi.Ranking[];
  stages: OpenApi.StageWithStageItems[];
  teams: OpenApi.FullTeamWithPlayers[];
  tournament: OpenApi.Tournament;
  /** The home page's list. By default the tournament, which the organizer manages. */
  tournaments?: OpenApi.TournamentWithAccess[];
};

/** A change that the page asked for. */
export type Write = { body: unknown; method: string; path: string };

/** An answer to a change: by default the `SuccessResponse` most changes answer with. */
export type WriteAnswer = { json: unknown; status?: number };

function json(route: Route, data: unknown, status = 200) {
  return route.fulfill({ json: data, status });
}

/**
 * The API of one tournament, for the workspace, the Details pages and the home page. GETs answer
 * from `state` as it is when they arrive. Changes are recorded with their bodies, and `answer`
 * can answer one, or hold it back by returning a promise.
 */
export async function tournamentApi(
  page: Page,
  overrides: Partial<ApiState> = {},
  answer?: (write: Write) => WriteAnswer | undefined | Promise<WriteAnswer | undefined>,
) {
  const state: ApiState = {
    canManage: true,
    nextStageRankings: {},
    players: [],
    rankings: [ranking()],
    stages: [],
    teams,
    tournament: tournament(),
    ...overrides,
  };
  const writes: Write[] = [];

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== 'GET') {
      const write = { body: request.postDataJSON() as unknown, method: request.method(), path };
      writes.push(write);
      const reply = (await answer?.(write)) ?? {
        json: { success: true } satisfies OpenApi.SuccessResponse,
      };
      return json(route, reply.json, reply.status);
    }

    const details = {
      players: state.players,
      rankings: state.rankings,
      stages: state.stages,
      standings: {},
      teams: state.teams,
      tournament: state.tournament,
    } satisfies OpenApi.TournamentDetails;
    const responses: Record<string, unknown> = {
      '/api/clubs': [],
      '/api/tournaments': state.tournaments ?? [
        { ...state.tournament, can_manage: state.canManage },
      ],
      '/api/tournaments/7': state.tournament,
      '/api/tournaments/7/access': { can_manage: state.canManage },
      '/api/tournaments/7/details': details,
      '/api/users/me': user,
    };
    if (path === '/api/tournaments/7/workspace') {
      return state.canManage
        ? json(route, {
            data: {
              ...details,
              available_inputs: {},
              next_stage_rankings: state.nextStageRankings,
            } satisfies OpenApi.TournamentWorkspace,
          })
        : json(route, { detail: "You don't have access to this tournament" }, 403);
    }
    return Object.hasOwn(responses, path)
      ? json(route, { data: responses[path] })
      : json(route, { detail: `Unexpected request: ${path}` }, 404);
  });

  return { state, writes };
}

/** Signs the browser in, as logging in would: the session cookie and who is signed in. */
export async function signIn(context: BrowserContext, session = 'session', started = 1) {
  await context.addInitScript((startedAt) => {
    localStorage.setItem(
      'bracket:session',
      JSON.stringify({ name: 'Owner', started: startedAt, user_id: 1 }),
    );
  }, started);
  await context.addCookies([
    { httpOnly: true, name: 'bracket_session', url: ORIGIN, value: session },
  ]);
}

/** Refreshes every query, as polling does, without waiting a minute between assertions. */
export async function refresh(page: Page) {
  await page.evaluate(async () => {
    const modulePath = '/src/app/query-client.ts';
    const { queryClient } = await import(/* @vite-ignore */ modulePath);
    await queryClient.invalidateQueries();
  });
}

/** A promise that the test settles: for answers that arrive when the test says so. */
export function deferred() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}
