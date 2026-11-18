import type { AxiosError } from 'axios';

import { client } from '../openapi/client.gen';
import * as OpenApi from '../openapi';
import { syncClock } from './clock';
import { readSession } from './hooks';
import type { Session, TournamentBundle } from './types';
import { getApiBaseUrl, isNumericIdentifier } from './urls';

declare module 'axios' {
  interface InternalAxiosRequestConfig {
    /** The session the request was sent in: when it started, or `null` without one. */
    sentInSession?: number | null;
  }
}

export const TOURNAMENT_BUNDLE_QUERY_KEY = ['tournament-bundle'];

/**
 * How long a read may take. A connection that stays open without an answer would otherwise keep a
 * page loading, or its refresh pending, until the browser gives up.
 */
export const READ_TIMEOUT_MS = 30_000;

/** Their 401 says that the credentials typed in are wrong, not that a session ended. */
const CREDENTIAL_SUBMISSIONS = new Set(['/api/token', '/api/users/register']);

let unauthorizedHandler: (() => void) | null = null;

/**
 * Called once when a request of the current session is refused because that session ended.
 * Returns a function that removes the handler again.
 */
export function setUnauthorizedHandler(handler: () => void) {
  unauthorizedHandler = handler;
  return () => {
    if (unauthorizedHandler === handler) unauthorizedHandler = null;
  };
}

function sessionMarker(session: Session) {
  // Sessions remembered by an earlier version of the page have no start time.
  return session == null ? null : (session.started ?? 0);
}

function getResponseStatus(error: unknown) {
  return (error as AxiosError | undefined)?.response?.status;
}

/**
 * Whether a refused request means that the session this page has now has ended. An answer to a
 * request of an earlier session, which arrives after logging in again, doesn't end the new one.
 */
function endsCurrentSession(error: unknown) {
  const config = (error as AxiosError | undefined)?.config;
  if (getResponseStatus(error) !== 401 || config == null) return false;
  if (CREDENTIAL_SUBMISSIONS.has(new URL(config.url ?? '', window.location.origin).pathname)) {
    return false;
  }
  return config.sentInSession != null && config.sentInSession === sessionMarker(readSession());
}

export function configureApiClient() {
  client.setConfig({
    baseURL: getApiBaseUrl(),
    // The session is an HttpOnly cookie. Requests to the page's own origin always carry it; this
    // also sends it to an API on another origin of the same site.
    withCredentials: true,
    // The API refuses changes signed in with the cookie unless they carry this header, which other
    // sites can't add (CSRF protection).
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  });

  client.instance.interceptors.request.use((config) => {
    config.sentInSession = sessionMarker(readSession());
    // Reads give up eventually, so that the page can offer to try again. Changes don't: one that
    // takes long can still be saved, so the page mustn't report it as failed.
    if (config.method?.toLowerCase() === 'get') config.timeout ||= READ_TIMEOUT_MS;
    return config;
  });
  client.instance.interceptors.response.use(
    (response) => {
      syncClock(response.headers.date);
      return response;
    },
    (error: unknown) => {
      if (endsCurrentSession(error)) unauthorizedHandler?.();
      return Promise.reject(error);
    },
  );
}

export async function fetchTournament(tournamentKey: string, signal?: AbortSignal) {
  if (!isNumericIdentifier(tournamentKey)) {
    const { data } = await OpenApi.getTournamentsApiTournamentsGet({
      query: { endpoint_name: tournamentKey },
      signal,
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
    signal,
    throwOnError: true,
  });
  return data.data;
}

/** The Details pages: one answer for everything, which the API keeps ready for every visitor. */
async function fetchDetailsBundle(
  tournamentKey: string,
  isAuthenticated: boolean,
  signal?: AbortSignal,
): Promise<TournamentBundle> {
  const tournamentId = isNumericIdentifier(tournamentKey)
    ? Number(tournamentKey)
    : (await fetchTournament(tournamentKey, signal)).id;
  const path = { tournament_id: tournamentId };

  const [details, access] = await Promise.all([
    OpenApi.getTournamentDetailsByIdApiTournamentsTournamentIdDetailsGet({
      path,
      signal,
      throwOnError: true,
    }),
    // Visitors can't manage anything, so only someone who is signed in asks.
    isAuthenticated
      ? OpenApi.getTournamentAccessApiTournamentsTournamentIdAccessGet({
          path,
          signal,
          throwOnError: true,
        })
      : null,
  ]);
  const { players, rankings, stages, standings, teams, tournament } = details.data.data;

  return {
    availableInputs: {},
    canManage: access?.data.data.can_manage ?? false,
    nextStageRankings: {},
    players,
    rankings,
    stages,
    standings,
    teams,
    tournament,
  };
}

/**
 * The workspace: one answer, from one database snapshot, so that the stages, the choices for
 * their slots, the standings and who would advance agree. Someone who can't manage the
 * tournament gets its Details pages' data instead.
 */
async function fetchWorkspaceBundle(
  tournamentKey: string,
  signal?: AbortSignal,
): Promise<TournamentBundle> {
  if (!isNumericIdentifier(tournamentKey)) {
    throw new Error('Tournament management routes require a numeric tournament id.');
  }

  try {
    const { data } = await OpenApi.getTournamentWorkspaceApiTournamentsTournamentIdWorkspaceGet({
      path: { tournament_id: Number(tournamentKey) },
      signal,
      throwOnError: true,
    });
    const { available_inputs, next_stage_rankings, ...workspace } = data.data;
    return {
      ...workspace,
      availableInputs: available_inputs,
      canManage: true,
      nextStageRankings: next_stage_rankings,
    };
  } catch (error) {
    if (getResponseStatus(error) !== 403) throw error;
    return fetchDetailsBundle(tournamentKey, false, signal);
  }
}

/**
 * Everything a tournament page shows. `signal` cancels its requests, as when the page is left
 * before they finish.
 */
export function fetchTournamentBundle(
  tournamentKey: string,
  dashboardMode: boolean,
  isAuthenticated: boolean,
  signal?: AbortSignal,
): Promise<TournamentBundle> {
  return dashboardMode
    ? fetchDetailsBundle(tournamentKey, isAuthenticated, signal)
    : fetchWorkspaceBundle(tournamentKey, signal);
}
