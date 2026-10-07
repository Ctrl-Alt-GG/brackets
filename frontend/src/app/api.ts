import { client } from '../openapi/client.gen';
import * as OpenApi from '../openapi';
import { readSession } from './hooks';
import type { Session, TournamentBundle } from './types';
import { getApiBaseUrl, isNumericIdentifier } from './utils';

function getResponseStatus(error: unknown) {
  return (error as { response?: { status?: number } })?.response?.status;
}

function isAuthorizationError(error: unknown) {
  const status = getResponseStatus(error);
  return status === 401 || status === 403;
}

export const TOURNAMENT_BUNDLE_QUERY_KEY = ['tournament-bundle'];

let unauthorizedHandler: (() => void) | null = null;
let unauthorizedInterceptorAttached = false;

export function setUnauthorizedHandler(handler: () => void) {
  unauthorizedHandler = handler;
}

export function configureApiClient(session: Session) {
  client.setConfig({
    auth: session?.access_token,
    baseURL: getApiBaseUrl(),
    // Endpoints whose auth dependency is resolved manually are not marked as
    // secured in the OpenAPI schema, so the generated `auth` option never
    // reaches them. Sending the header here covers every request.
    headers: { Authorization: session ? `Bearer ${session.access_token}` : null },
  });

  if (!unauthorizedInterceptorAttached) {
    unauthorizedInterceptorAttached = true;
    client.instance.interceptors.response.use(
      (response) => response,
      (error: unknown) => {
        if (getResponseStatus(error) === 401 && readSession()) {
          unauthorizedHandler?.();
        }
        return Promise.reject(error);
      },
    );
  }
}

export async function fetchTournament(tournamentKey: string, dashboardMode: boolean) {
  if (!isNumericIdentifier(tournamentKey)) {
    if (!dashboardMode) {
      throw new Error('Tournament management routes require a numeric tournament id.');
    }

    const { data } = await OpenApi.getTournamentsApiTournamentsGet({
      query: { endpoint_name: tournamentKey },
      throwOnError: true,
    });
    const tournament = data.data[0];
    if (!tournament) {
      throw new Error(`No tournament has the Details link "${tournamentKey}".`);
    }
    return tournament;
  }

  const { data } = await OpenApi.getTournamentApiTournamentsTournamentIdGet({
    path: { tournament_id: Number(tournamentKey) },
    throwOnError: true,
  });
  return data.data;
}

function withoutDraftRounds(stages: OpenApi.StageWithStageItems[]) {
  return stages.map((stage) => ({
    ...stage,
    stage_items: stage.stage_items.map((stageItem) => ({
      ...stageItem,
      rounds: stageItem.rounds.filter((round) => !round.is_draft),
    })),
  }));
}

/** Everything a tournament page shows, loaded together so all sections agree with each other. */
export async function fetchTournamentBundle(
  tournamentKey: string,
  dashboardMode: boolean,
  isAuthenticated: boolean,
): Promise<TournamentBundle> {
  const tournament = await fetchTournament(tournamentKey, dashboardMode);
  const path = { tournament_id: tournament.id };
  let canManage = isAuthenticated;
  let stages: OpenApi.StageWithStageItems[];

  // Only organizers of the tournament may see draft rounds, so asking for them tells whether the
  // signed-in user can manage it.
  try {
    const { data } = await OpenApi.getStagesApiTournamentsTournamentIdStagesGet({
      path,
      query: { no_draft_rounds: !isAuthenticated },
      throwOnError: true,
    });
    stages = data.data;
  } catch (error) {
    if (!isAuthenticated || !isAuthorizationError(error)) {
      throw error;
    }

    canManage = false;
    const { data } = await OpenApi.getStagesApiTournamentsTournamentIdStagesGet({
      path,
      query: { no_draft_rounds: true },
      throwOnError: true,
    });
    stages = data.data;
  }

  const [players, teams, rankings, standings] = await Promise.all([
    OpenApi.getPlayersApiTournamentsTournamentIdPlayersGet({
      path,
      query: { limit: 100, offset: 0, sort_by: 'name', sort_direction: 'asc' },
      throwOnError: true,
    }),
    OpenApi.getTeamsApiTournamentsTournamentIdTeamsGet({
      path,
      query: { limit: 100, offset: 0, sort_by: 'name', sort_direction: 'asc' },
      throwOnError: true,
    }),
    OpenApi.getRankingsApiTournamentsTournamentIdRankingsGet({ path, throwOnError: true }),
    OpenApi.getStandingsApiTournamentsTournamentIdStandingsGet({ path, throwOnError: true }),
  ]);

  const managementData =
    canManage && !dashboardMode
      ? await Promise.all([
          OpenApi.getAvailableInputsApiTournamentsTournamentIdAvailableInputsGet({
            path,
            throwOnError: true,
          }),
          OpenApi.getNextStageRankingsApiTournamentsTournamentIdNextStageRankingsGet({
            path,
            throwOnError: true,
          }),
        ])
      : null;

  return {
    availableInputs: managementData?.[0].data.data ?? {},
    canManage,
    nextStageRankings: managementData?.[1].data.data ?? {},
    players: players.data.data.players,
    rankings: rankings.data.data,
    // The Details pages show organizers exactly what everyone else sees.
    stages: dashboardMode ? withoutDraftRounds(stages) : stages,
    standings: standings.data.data,
    teams: teams.data.data.teams,
    tournament,
  };
}
