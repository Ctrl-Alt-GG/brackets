import { client } from '../openapi/client.gen';
import * as OpenApi from '../openapi';
import type { AuthFeatures, TournamentBundle, Session } from './types';
import { getApiBaseUrl, isNumericIdentifier, readSession } from './utils';

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

export async function unwrap<T>(promise: Promise<{ data: T }>) {
  const response = await promise;
  return response.data;
}

export async function fetchAuthFeatures(): Promise<AuthFeatures> {
  const response = await fetch(`${getApiBaseUrl()}/api/auth/features`, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Unable to load auth features (${response.status}).`);
  }

  const payload = (await response.json()) as {
    data: {
      password_reset_enabled: boolean;
      user_registration_enabled: boolean;
    };
  };

  return {
    passwordResetEnabled: payload.data.password_reset_enabled,
    userRegistrationEnabled: payload.data.user_registration_enabled,
  };
}

export async function fetchTournaments(
  filter?: 'ALL' | 'OPEN' | 'ARCHIVED',
  endpointName?: string,
  accessToken?: string,
) {
  const response = await unwrap(
    OpenApi.getTournamentsApiTournamentsGet({
      auth: accessToken,
      query: {
        endpoint_name: endpointName,
        filter_: filter,
      },
      throwOnError: true,
    }),
  );

  return response.data;
}

export async function fetchCurrentUserName(accessToken?: string) {
  const response = await unwrap(
    OpenApi.getUserApiUsersMeGet({
      auth: accessToken,
      throwOnError: true,
    }),
  );
  return response.data.name;
}

export async function fetchTournament(
  tournamentKey: string,
  dashboardMode: boolean,
  accessToken?: string,
) {
  if (!isNumericIdentifier(tournamentKey)) {
    if (!dashboardMode) {
      throw new Error('Tournament management routes require a numeric tournament id.');
    }

    const tournaments = await fetchTournaments(undefined, tournamentKey, accessToken);
    const tournament = tournaments[0];
    if (!tournament) {
      throw new Error(`No tournament matches the dashboard endpoint "${tournamentKey}".`);
    }
    return tournament;
  }

  const response = await unwrap(
    OpenApi.getTournamentApiTournamentsTournamentIdGet({
      auth: accessToken,
      path: { tournament_id: Number(tournamentKey) },
      throwOnError: true,
    }),
  );
  return response.data;
}

export async function fetchTournamentBundle(
  tournamentKey: string,
  dashboardMode: boolean,
  isAuthenticated: boolean,
  accessToken?: string,
): Promise<TournamentBundle> {
  const tournament = await fetchTournament(tournamentKey, dashboardMode, accessToken);
  const tournamentId = tournament.id;
  let canManage = isAuthenticated;
  let stageResponse: { data: OpenApi.StageWithStageItems[] };

  try {
    stageResponse = await unwrap(
      OpenApi.getStagesApiTournamentsTournamentIdStagesGet({
        auth: accessToken,
        path: { tournament_id: tournamentId },
        query: { no_draft_rounds: dashboardMode || !isAuthenticated },
        throwOnError: true,
      }),
    );
  } catch (error) {
    if (!isAuthenticated || dashboardMode || !isAuthorizationError(error)) {
      throw error;
    }

    canManage = false;
    stageResponse = await unwrap(
      OpenApi.getStagesApiTournamentsTournamentIdStagesGet({
        auth: accessToken,
        path: { tournament_id: tournamentId },
        query: { no_draft_rounds: true },
        throwOnError: true,
      }),
    );
  }
  const stages = stageResponse.data;

  const [playersResponse, teamsResponse, rankingsResponse, standingsResponse] = await Promise.all([
    unwrap(
      OpenApi.getPlayersApiTournamentsTournamentIdPlayersGet({
        auth: accessToken,
        path: { tournament_id: tournamentId },
        query: { limit: 100, offset: 0, sort_by: 'name', sort_direction: 'asc' },
        throwOnError: true,
      }),
    ),
    unwrap(
      OpenApi.getTeamsApiTournamentsTournamentIdTeamsGet({
        auth: accessToken,
        path: { tournament_id: tournamentId },
        query: { limit: 100, offset: 0, sort_by: 'name', sort_direction: 'asc' },
        throwOnError: true,
      }),
    ),
    unwrap(
      OpenApi.getRankingsApiTournamentsTournamentIdRankingsGet({
        auth: accessToken,
        path: { tournament_id: tournamentId },
        throwOnError: true,
      }),
    ),
    unwrap(
      OpenApi.getStandingsApiTournamentsTournamentIdStandingsGet({
        auth: accessToken,
        path: { tournament_id: tournamentId },
        throwOnError: true,
      }),
    ),
  ]);

  const managementData = canManage
    ? await Promise.all([
        unwrap(
          OpenApi.getAvailableInputsApiTournamentsTournamentIdAvailableInputsGet({
            auth: accessToken,
            path: { tournament_id: tournamentId },
            throwOnError: true,
          }),
        ),
        unwrap(
          OpenApi.getNextStageRankingsApiTournamentsTournamentIdNextStageRankingsGet({
            auth: accessToken,
            path: { tournament_id: tournamentId },
            throwOnError: true,
          }),
        ),
      ])
    : null;

  const [availableInputsResponse, nextStageRankingsResponse] = managementData ?? [
    { data: {} },
    { data: {} },
  ];

  return {
    canManage,
    availableInputs: availableInputsResponse.data,
    nextStageRankings: nextStageRankingsResponse.data,
    players: playersResponse.data.players,
    rankings: rankingsResponse.data,
    stages,
    standings: standingsResponse.data,
    teams: teamsResponse.data.teams,
    tournament,
  };
}
