import type { AxiosError } from 'axios';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import * as OpenApi from '../openapi';
import type { FlattenedMatch, Session } from './types';

const SESSION_STORAGE_KEY = 'login';

export function cx(...values: ClassValue[]) {
  return twMerge(clsx(values));
}

export function isNumericIdentifier(value: string) {
  return /^\d+$/.test(value);
}

export function toNumber(value: FormDataEntryValue | null, fallback = 0) {
  if (typeof value !== 'string') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function toOptionalNumber(value: FormDataEntryValue | null) {
  if (typeof value !== 'string' || value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function toOptionalString(value: FormDataEntryValue | null) {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

export function toCheckbox(value: FormDataEntryValue | null) {
  return value === 'on';
}

export function readSession(): Session {
  if (typeof window === 'undefined') return null;

  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as OpenApi.Token;
    if (!parsed?.access_token) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeSession(nextSession: Session) {
  if (typeof window === 'undefined') return;

  if (nextSession) {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(nextSession));
    return;
  }

  window.localStorage.removeItem(SESSION_STORAGE_KEY);
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
  if (!value) return 'Unscheduled';

  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function normalizeDashboardEndpoint(value: unknown) {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

type StageItemInput =
  | OpenApi.StageItemInputTentative
  | OpenApi.StageItemInputFinal
  | OpenApi.StageItemInputEmpty;

export function hasTeam(input: StageItemInput | null): input is OpenApi.StageItemInputFinal {
  return input != null && 'team' in input && input.team != null;
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
