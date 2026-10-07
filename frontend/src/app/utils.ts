import type { AxiosError } from 'axios';
import { clsx, type ClassValue } from 'clsx';
import { format, isThisYear, isToday, isValid, parseISO } from 'date-fns';
import { twMerge } from 'tailwind-merge';
import { z } from 'zod';

import * as OpenApi from '../openapi';
import type { FlattenedMatch } from './types';

export function cx(...values: ClassValue[]) {
  return twMerge(clsx(values));
}

export function isNumericIdentifier(value: string) {
  return /^\d+$/.test(value);
}

export function getApiBaseUrl() {
  const runtimeConfig =
    typeof window !== 'undefined' ? window.__BRACKET_RUNTIME_CONFIG__ : undefined;
  const runtimeValue = runtimeConfig?.apiBaseUrl?.trim();

  return normalizeApiBaseUrl(
    runtimeValue || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8400',
  );
}

// Callers append `/api/...` themselves, so a configured value ending in `/api` would double it.
function normalizeApiBaseUrl(value: string) {
  return value.replace(/\/+$/, '').replace(/\/api$/, '');
}

export function getErrorMessage(error: unknown) {
  const fallback = 'The request failed. Check the backend connection and your credentials.';
  const axiosError = error as AxiosError<{
    detail?: string | Array<{ loc: string[]; msg: string }>;
  }>;
  const detail = axiosError?.response?.data?.detail;

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    return `${first.loc.join(' > ')}: ${first.msg}`;
  }

  if (typeof detail === 'string' && detail) return detail;
  if (axiosError?.message) return axiosError.message;

  return fallback;
}

export function formatDateTime(value: string | null) {
  if (!value) return 'Not scheduled yet';

  const date = parseISO(value);
  if (!isValid(date)) return value;
  return format(date, isThisYear(date) ? 'MMM d, p' : 'PP, p');
}

/** Like `formatDateTime`, but an event mostly runs on one day, so today's matches show the time. */
export function formatMatchTime(value: string | null) {
  const date = value ? parseISO(value) : null;
  if (!date || !isValid(date) || !isToday(date)) return formatDateTime(value);
  return `Today, ${format(date, 'p')}`;
}

/** The value of a `datetime-local` input for an ISO timestamp, in the viewer's time zone. */
export function toDateTimeLocal(value: string) {
  return format(parseISO(value), "yyyy-MM-dd'T'HH:mm");
}

/** A `datetime-local` value, sent as the UTC timestamp the API expects. */
export const zLocalDateTime = z
  .string()
  .min(1, 'Pick a date and time')
  .transform((value) => new Date(value).toISOString());

export function normalizeDashboardEndpoint(value: unknown) {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

/**
 * The tournament's Details page. Its custom link only resolves while the page is enabled, and the
 * tournament id always does.
 */
export function publicTournamentPath(tournament: OpenApi.Tournament) {
  const endpoint = tournament.dashboard_public
    ? normalizeDashboardEndpoint(tournament.dashboard_endpoint)
    : null;
  return `/tournaments/${endpoint ?? tournament.id}/dashboard`;
}

export type TournamentPhase = 'finished' | 'running' | 'upcoming';

export function tournamentPhase(tournament: OpenApi.Tournament, now = Date.now()): TournamentPhase {
  if (tournament.status !== 'OPEN') return 'finished';
  return new Date(tournament.start_time).getTime() > now ? 'upcoming' : 'running';
}

export const TOURNAMENT_PHASE_LABELS: Record<TournamentPhase, string> = {
  finished: 'Finished',
  running: 'Running',
  upcoming: 'Upcoming',
};

export function tournamentDateLabel(tournament: OpenApi.Tournament) {
  const date = formatDateTime(tournament.start_time);
  return tournamentPhase(tournament) === 'upcoming' ? `Starts ${date}` : `Started ${date}`;
}

// Mirrors the backend: open tournaments are always public, archived ones only with this setting,
// and the custom link only resolves with it.
export const DETAILS_PAGE_DESCRIPTION =
  'Tournaments are public until they are archived. With this on, the Details link works and the tournament stays public after it is archived.';

type StageItemInput =
  | OpenApi.StageItemInputTentative
  | OpenApi.StageItemInputFinal
  | OpenApi.StageItemInputEmpty;

export function hasTeam(input: StageItemInput | null): input is OpenApi.StageItemInputFinal {
  return input != null && 'team' in input && input.team != null;
}

/** The team behind an input, once it is known. */
export function inputTeamId(input: StageItemInput | null) {
  return hasTeam(input) ? input.team_id : null;
}

export function involvesTeam(
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive,
  teamId: number,
) {
  return (
    inputTeamId(match.stage_item_input1) === teamId ||
    inputTeamId(match.stage_item_input2) === teamId
  );
}

export function isBracket(stageItem: OpenApi.StageItemWithRounds) {
  return stageItem.type === 'SINGLE_ELIMINATION';
}

export function sortTeamsByName<T extends { name: string }>(teams: T[]) {
  return teams.toSorted((left, right) => left.name.localeCompare(right.name));
}

export function isEmptySlot(input: StageItemInput) {
  return input.team_id == null && input.winner_from_stage_item_id == null;
}

export function activeTeamInputs(stageItem: OpenApi.StageItemWithRounds) {
  return stageItem.inputs.filter(
    (input): input is OpenApi.StageItemInputFinal => hasTeam(input) && input.team.active,
  );
}

/**
 * The teams of a stage item with their results, best first. The backend ranks them, in the same
 * order in which teams advance to the next stage.
 */
export function stageItemStandings(
  stageItem: OpenApi.StageItemWithRounds,
  standings: Record<string, OpenApi.StageItemInputStanding[]>,
) {
  const inputs = new Map(stageItem.inputs.filter(hasTeam).map((input) => [input.id, input]));
  return (standings[String(stageItem.id)] ?? []).flatMap((standing) => {
    const input = inputs.get(standing.stage_item_input_id);
    return input ? [{ input, standing }] : [];
  });
}

/** Swiss stage items rank teams by an ELO rating instead of points. */
export function pointsLabel(stageItem: OpenApi.StageItemWithRounds) {
  return stageItem.type === 'SWISS' ? 'Rating' : 'Points';
}

export function formatPoints(points: string) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2, useGrouping: false }).format(
    Number(points),
  );
}

export function formatScoreDifference(standing: OpenApi.StageItemInputStanding) {
  return new Intl.NumberFormat(undefined, { signDisplay: 'exceptZero' }).format(
    standing.score_for - standing.score_against,
  );
}

/** For running text, such as "2.5 points" or "rating 1216". */
export function pointsPhrase(stageItem: OpenApi.StageItemWithRounds, points: string) {
  if (stageItem.type === 'SWISS') return `rating ${formatPoints(points)}`;
  return `${formatPoints(points)} ${Number(points) === 1 ? 'point' : 'points'}`;
}

export function inputLabel(
  input: StageItemInput | null,
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>,
) {
  if (!input) return 'TBD';
  if (hasTeam(input)) return input.team.name;
  if (input.winner_from_stage_item_id != null) {
    const stageItem = stageItemsById.get(input.winner_from_stage_item_id);
    const sourceName = stageItem?.name || stageItem?.type_name;
    return sourceName ? `${sourceName} #${input.winner_position}` : 'TBD';
  }

  return 'TBD';
}

export function isScored(match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive) {
  return match.stage_item_input1_score !== 0 || match.stage_item_input2_score !== 0;
}

export type MatchOutcome = 1 | 2 | 'draw' | null;

/** Scores are the only completion signal the API exposes, so an unplayed match reads as 0-0. */
export function matchWinner(
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive,
): MatchOutcome {
  if (!isScored(match)) return null;
  if (match.stage_item_input1_score > match.stage_item_input2_score) return 1;
  if (match.stage_item_input2_score > match.stage_item_input1_score) return 2;
  return 'draw';
}

export type MatchStatus = 'finished' | 'live' | 'scheduled' | 'waiting';

export function matchStatus(
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive,
  now = Date.now(),
): MatchStatus {
  if (isScored(match)) return 'finished';
  if (match.stage_item_input1 == null || match.stage_item_input2 == null) return 'waiting';
  if (match.start_time) {
    const start = new Date(match.start_time).getTime();
    if (Number.isFinite(start) && now >= start && now < start + match.duration_minutes * 60_000) {
      return 'live';
    }
  }
  return 'scheduled';
}

export const MATCH_STATUS_LABELS: Record<MatchStatus, string> = {
  finished: 'Finished',
  live: 'Playing now',
  scheduled: 'Scheduled',
  waiting: 'Waiting for teams',
};

/**
 * Only activating another stage changes `is_active`, so the last stage stays active after its
 * final match and after the tournament is archived.
 */
export function isStageHappeningNow(
  stage: OpenApi.StageWithStageItems,
  tournament: OpenApi.Tournament,
) {
  if (tournament.status !== 'OPEN' || !stage.is_active) return false;
  return stage.stage_items.some(
    (stageItem) =>
      // Swiss rounds are drawn one at a time, so a Swiss stage can always get another round.
      stageItem.type === 'SWISS' ||
      stageItem.rounds.some(
        (round) => !round.is_draft && round.matches.some((match) => !isScored(match)),
      ),
  );
}

/** From matches sorted by time: the one being played, otherwise the earliest without a result. */
export function nextMatch(entries: FlattenedMatch[]) {
  return (
    entries.find(({ match }) => matchStatus(match) === 'live') ??
    entries.find(({ match }) => !isScored(match)) ??
    null
  );
}

export function compareMatchesByTime(left: FlattenedMatch, right: FlattenedMatch) {
  const leftTime = left.match.start_time
    ? new Date(left.match.start_time).getTime()
    : Number.MAX_SAFE_INTEGER;
  const rightTime = right.match.start_time
    ? new Date(right.match.start_time).getTime()
    : Number.MAX_SAFE_INTEGER;
  if (leftTime !== rightTime) return leftTime - rightTime;
  if (left.round.id !== right.round.id) return left.round.id - right.round.id;
  return left.match.id - right.match.id;
}

export function flattenMatches(stages: OpenApi.StageWithStageItems[]) {
  return stages.flatMap((stage) =>
    stage.stage_items.flatMap((stageItem) =>
      stageItem.rounds.flatMap((round) =>
        round.matches.map((match) => ({
          match,
          round,
          stage,
          stageItem,
        })),
      ),
    ),
  );
}
