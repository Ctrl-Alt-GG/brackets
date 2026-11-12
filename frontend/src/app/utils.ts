import type { AxiosError } from 'axios';
import { clsx, type ClassValue } from 'clsx';
import { format, isThisYear, isToday, isValid, parseISO } from 'date-fns';
import { twMerge } from 'tailwind-merge';

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

  // Without one, the API is on the page's own origin, as behind the Vite dev server's proxy.
  return normalizeApiBaseUrl(runtimeValue || import.meta.env.VITE_API_BASE_URL || '');
}

// Callers append `/api/...` themselves, so a configured value ending in `/api` would double it.
function normalizeApiBaseUrl(value: string) {
  return value.replace(/\/+$/, '').replace(/\/api$/, '');
}

/**
 * Where an uploaded logo is served. The file name changes with every upload, so adding it makes
 * browsers fetch the new picture instead of showing the one they kept.
 */
export function tournamentLogoUrl(tournament: OpenApi.Tournament) {
  if (!tournament.logo_path) return null;
  const version = encodeURIComponent(tournament.logo_path);
  return `${getApiBaseUrl()}/api/tournaments/${tournament.id}/logo?v=${version}`;
}

export function teamLogoUrl(team: Pick<OpenApi.Team, 'id' | 'logo_path' | 'tournament_id'>) {
  if (!team.logo_path) return null;
  const version = encodeURIComponent(team.logo_path);
  return `${getApiBaseUrl()}/api/tournaments/${team.tournament_id}/teams/${team.id}/logo?v=${version}`;
}

/** The login page, which brings the organizer back to `from` once they are signed in. */
export function loginPath(from: string) {
  const isWorthReturningTo =
    from !== '/' && !/^\/(login|create-account|password-reset)\b/.test(from);
  return isWorthReturningTo ? `/login?next=${encodeURIComponent(from)}` : '/login';
}

/** Only a path of this site: `next` is in the address bar, where anyone can put anything. */
export function safeNextPath(next: string | null) {
  return next != null && /^\/(?![/\\])/.test(next) ? next : '/';
}

export function getErrorMessage(error: unknown) {
  const fallback = 'The request failed. Check your connection and try again.';
  const axiosError = error as AxiosError<{
    detail?: string | Array<{ loc: string[]; msg: string }>;
  }>;
  const response = axiosError?.response;
  const detail = response?.data?.detail;

  if (Array.isArray(detail) && detail.length > 0) {
    // "Value error, " is how the API prefixes the message of its own checks.
    return detail[0].msg.replace(/^Value error, /, '');
  }

  if (typeof detail === 'string' && detail) return detail;

  // The request limit of the API answers without a `detail`.
  if (response?.status === 429) {
    const seconds = Number(response.headers?.['retry-after']);
    const minutes = Math.ceil(seconds / 60);
    return Number.isFinite(seconds) && seconds > 0
      ? `Too many attempts. Try again in ${minutes === 1 ? 'a minute' : `${minutes} minutes`}.`
      : 'Too many attempts. Try again in a few minutes.';
  }

  if (axiosError?.message) return axiosError.message;

  return fallback;
}

/** Groups items by a key, keeping the order in which the keys first appear. */
export function groupBy<T, K>(items: T[], key: (item: T) => K) {
  const groups = new Map<K, T[]>();
  for (const item of items) {
    const group = groups.get(key(item));
    if (group) group.push(item);
    else groups.set(key(item), [item]);
  }
  return groups;
}

// Dates and times follow the visitor's own language settings: "15:30" where that is how a time
// is written, "3:30 PM" where that is.
const TIME_FORMAT = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });
const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' });
const DATE_WITH_YEAR_FORMAT = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});

export function formatTime(date: Date) {
  return TIME_FORMAT.format(date);
}

export function formatDateTime(value: string | null) {
  if (!value) return 'Not scheduled yet';

  const date = parseISO(value);
  if (!isValid(date)) return value;
  const day = (isThisYear(date) ? DATE_FORMAT : DATE_WITH_YEAR_FORMAT).format(date);
  return `${day}, ${formatTime(date)}`;
}

/** Like `formatDateTime`, but an event mostly runs on one day, so today's matches show the time. */
export function formatMatchTime(value: string | null) {
  const date = value ? parseISO(value) : null;
  if (!date || !isValid(date) || !isToday(date)) return formatDateTime(value);
  return `Today, ${formatTime(date)}`;
}

/** The value of a `datetime-local` input for an ISO timestamp, in the viewer's time zone. */
export function toDateTimeLocal(value: string) {
  return format(parseISO(value), "yyyy-MM-dd'T'HH:mm");
}

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

// How long after its last match a tournament still counts as running. Swiss rounds are drawn one
// at a time, so between two of them every match has a result for a while.
const FINISHED_AFTER_MS = 3 * 60 * 60 * 1000;

/**
 * Archiving a tournament is the organizer's call and easily forgotten, so a tournament whose
 * matches all have a result is finished too, a few hours after the last one.
 */
export function tournamentPhase(tournament: OpenApi.Tournament, now = Date.now()): TournamentPhase {
  if (tournament.status !== 'OPEN') return 'finished';
  if (new Date(tournament.start_time).getTime() > now) return 'upcoming';

  const allPlayed =
    tournament.matches_total > 0 && tournament.matches_played === tournament.matches_total;
  const lastMatchEnd = tournament.last_match_end
    ? new Date(tournament.last_match_end).getTime()
    : null;
  if (allPlayed && lastMatchEnd != null && now - lastMatchEnd > FINISHED_AFTER_MS) {
    return 'finished';
  }
  return 'running';
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

/** Whether the Bracket page draws the stage item: its knockout bracket, or its Swiss rounds. */
export function hasBracketView(stageItem: OpenApi.StageItemWithRounds) {
  return isBracket(stageItem) || stageItem.type === 'SWISS';
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

/** Whether the match has a result. An unplayed match reads 0-0, so the API says which it is. */
export function isScored(match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive) {
  return match.played;
}

export type MatchOutcome = 1 | 2 | 'draw' | null;

export function matchWinner(
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive,
): MatchOutcome {
  if (!isScored(match)) return null;
  if (match.stage_item_input1_score > match.stage_item_input2_score) return 1;
  if (match.stage_item_input2_score > match.stage_item_input1_score) return 2;
  return 'draw';
}

export type MatchStatus = 'awaiting' | 'finished' | 'live' | 'scheduled' | 'waiting';

/**
 * Where a match stands. The schedule is a plan, and matches run over: one that has started stays
 * in progress until its result is entered. It is `live` during its planned time, and `awaiting`
 * its result after that.
 */
export function matchStatus(
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive,
  now = Date.now(),
): MatchStatus {
  if (isScored(match)) return 'finished';
  // A slot that takes "Group A #1" has no team until that group is decided, so its match can't
  // be played yet, whatever the plan says.
  if (!hasTeam(match.stage_item_input1) || !hasTeam(match.stage_item_input2)) return 'waiting';
  if (match.start_time) {
    const start = new Date(match.start_time).getTime();
    if (Number.isFinite(start) && now >= start) {
      return now < start + match.duration_minutes * 60_000 ? 'live' : 'awaiting';
    }
  }
  return 'scheduled';
}

/** Being played, or played and waiting for its result. */
export function isInProgress(status: MatchStatus) {
  return status === 'live' || status === 'awaiting';
}

export const MATCH_STATUS_LABELS: Record<MatchStatus, string> = {
  awaiting: 'Awaiting result',
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

/** From matches sorted by time: the one in progress, otherwise the earliest without a result. */
export function nextMatch(entries: FlattenedMatch[]) {
  return (
    entries.find(({ match }) => isInProgress(matchStatus(match))) ??
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
