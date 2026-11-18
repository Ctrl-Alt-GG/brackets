/* Where a tournament, a stage and a match stand at a moment, by the server's clock. A page that
   stays open passes the time of `useServerNow`, so that what it shows follows the time. */

import * as OpenApi from '../openapi';
import { serverNow } from './clock';
import { hasTeam, isScored } from './matches';
import type { FlattenedMatch } from './types';

export type TournamentPhase = 'finished' | 'running' | 'upcoming';

// How long after its last match a tournament still counts as running.
const FINISHED_AFTER_MS = 3 * 60 * 60 * 1000;

/**
 * Archiving a tournament is the organizer's call and easily forgotten, so a tournament whose
 * matches all have a result is finished too, a few hours after the last one. Not while a Swiss
 * stage is active or still to come: its rounds are drawn one at a time, so between two of them,
 * or overnight at an event of several days, every published match has a result.
 */
export function tournamentPhase(
  tournament: OpenApi.Tournament,
  now = serverNow(),
): TournamentPhase {
  if (tournament.status !== 'OPEN') return 'finished';
  if (new Date(tournament.start_time).getTime() > now) return 'upcoming';

  const allPlayed =
    tournament.matches_total > 0 && tournament.matches_played === tournament.matches_total;
  const lastMatchEnd = tournament.last_match_end
    ? new Date(tournament.last_match_end).getTime()
    : null;
  if (
    allPlayed &&
    !tournament.more_rounds_possible &&
    lastMatchEnd != null &&
    now - lastMatchEnd > FINISHED_AFTER_MS
  ) {
    return 'finished';
  }
  return 'running';
}

export type MatchStatus = 'awaiting' | 'finished' | 'live' | 'scheduled' | 'waiting';

/**
 * Where a match stands. The schedule is a plan, and matches run over: one that has started stays
 * in progress until its result is entered. It is `live` during its planned time, and `awaiting`
 * its result after that.
 */
export function matchStatus(
  match: OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive,
  now = serverNow(),
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

// How long a Swiss stage whose matches all have a result still counts as happening after its
// latest round was drawn: the time a round takes, and the break before the next one.
const SWISS_ROUND_RECENT_MS = 3 * 60 * 60 * 1000;

/**
 * Whether the stage is being played: it has matches without a result. Only activating another
 * stage changes `is_active`, so the last stage stays active after its final match and after the
 * tournament is archived. Swiss rounds are drawn one at a time, so between two of them every match
 * has a result: a Swiss stage also counts while its latest round is recent.
 */
export function isStageHappeningNow(
  stage: OpenApi.StageWithStageItems,
  tournament: OpenApi.Tournament,
  now = serverNow(),
) {
  if (tournament.status !== 'OPEN' || !stage.is_active) return false;
  return stage.stage_items.some(
    (stageItem) =>
      stageItem.rounds.some(
        (round) => !round.is_draft && round.matches.some((match) => !isScored(match)),
      ) ||
      (stageItem.type === 'SWISS' &&
        stageItem.rounds.some(
          (round) => now - new Date(round.created).getTime() < SWISS_ROUND_RECENT_MS,
        )),
  );
}

/** From matches sorted by time: the one in progress, otherwise the earliest without a result. */
export function nextMatch(entries: FlattenedMatch[], now = serverNow()) {
  return (
    entries.find(({ match }) => isInProgress(matchStatus(match, now))) ??
    entries.find(({ match }) => !isScored(match)) ??
    null
  );
}
