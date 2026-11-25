import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Trans, useTranslation } from 'react-i18next';

import * as OpenApi from '../../openapi';
import {
  delayScheduleApiTournamentsTournamentIdDelaySchedulePostMutation,
  scheduleMatchesApiTournamentsTournamentIdScheduleMatchesPostMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { BigScreenLink } from '../components/big-screen';
import { MatchCard } from '../components/match-card';
import { MatchScoreEditor } from '../components/match-score-editor';
import type { FlattenedMatch } from '../types';
import { formatMatchTime } from '../format';
import { matchStatus } from '../tournament-rules';
import { cx, groupBy } from '../utils';
import { Surface, SurfaceHeading } from '../ui';

/** Names of a tournament's teams and players, for the notices about its conflicts. */
type Participants = {
  players: Map<number, string>;
  teams: Map<number, string>;
};

/** Why a match's team, or players of it, would have to be in two places at once. */
function ConflictNotice({
  conflicts,
  participants,
  tournamentId,
}: {
  conflicts: OpenApi.ScheduleConflict[];
  participants: Participants;
  tournamentId: number;
}) {
  const { t } = useTranslation();

  return (
    <ul className="mt-3 space-y-1 text-xs text-warning">
      {conflicts.map((conflict) => {
        const team = participants.teams.get(conflict.team_id) ?? '';
        const tournament = conflict.other_tournament_name;
        return (
          <li key={`${conflict.team_id}:${conflict.other_match_id}`}>
            {conflict.player_ids.length > 0
              ? t('workspace.conflictPlayers', {
                  count: conflict.player_ids.length,
                  players: conflict.player_ids
                    .map((playerId) => participants.players.get(playerId))
                    .join(', '),
                  team,
                  tournament,
                })
              : conflict.other_tournament_id === tournamentId
                ? t('workspace.conflictHere', { team })
                : t('workspace.conflictElsewhere', { team, tournament })}
          </li>
        );
      })}
    </ul>
  );
}

/** Matches sorted by time, grouped under the time they start. */
function TimeSlots({
  conflicts,
  entries,
  maxSlots,
  participants,
  size = 'md',
  stageItemsById,
  tournamentId,
}: {
  /** The conflicts of each match, by match id, for organizers. */
  conflicts?: Map<number, OpenApi.ScheduleConflict[]>;
  entries: FlattenedMatch[];
  maxSlots?: number;
  participants?: Participants;
  size?: 'lg' | 'md';
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  /** Set for organizers, who enter the results on the matches. */
  tournamentId?: number;
}) {
  const { t } = useTranslation();
  const slots = groupBy(entries, (entry) => entry.match.start_time ?? '');

  return (
    <div className="space-y-6">
      {[...slots.entries()].slice(0, maxSlots).map(([startTime, slotEntries]) => (
        <section className="space-y-3" key={startTime || 'unscheduled'}>
          <h3 className={cx('font-display font-semibold', size === 'lg' ? 'text-3xl' : 'text-xl')}>
            {formatMatchTime(startTime || null, t)}
          </h3>
          <div
            className={cx(
              'grid gap-3',
              size === 'lg' ? 'xl:grid-cols-2' : 'md:grid-cols-2 xl:grid-cols-3',
            )}
          >
            {slotEntries.map((entry) => {
              const matchConflicts = conflicts?.get(entry.match.id);
              return (
                <MatchCard
                  editor={
                    // A match is played once both teams are known.
                    tournamentId != null && matchStatus(entry.match) !== 'waiting' ? (
                      <MatchScoreEditor
                        entry={entry}
                        stageItemsById={stageItemsById}
                        tournamentId={tournamentId}
                      />
                    ) : undefined
                  }
                  entry={entry}
                  key={entry.match.id}
                  notice={
                    matchConflicts && participants && tournamentId != null ? (
                      <ConflictNotice
                        conflicts={matchConflicts}
                        participants={participants}
                        tournamentId={tournamentId}
                      />
                    ) : undefined
                  }
                  showTime={false}
                  size={size}
                  stageItemsById={stageItemsById}
                />
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

/**
 * For an event that runs late: moves what is still to come, without doing the sums. The round
 * being played, which is the latest one with a result, stays where it is.
 */
function DelayForm({ tournamentId }: { tournamentId: number }) {
  const { t } = useTranslation();
  const [minutes, setMinutes] = useState(15);
  const delay = useMutation({
    ...delayScheduleApiTournamentsTournamentIdDelaySchedulePostMutation(),
    meta: { successMessage: t('workspace.scheduleMoved') },
  });
  const move = (sign: 1 | -1) =>
    delay.mutate({ body: { minutes: sign * minutes }, path: { tournament_id: tournamentId } });

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-box border border-base-300 bg-base-100/40 p-4">
      <label className="fieldset p-0">
        <span className="fieldset-legend">{t('workspace.runningLate')}</span>
        <span className="flex flex-wrap items-center gap-2 text-sm">
          <Trans
            components={{
              minutes: (
                <input
                  aria-label={t('workspace.minutesToMove')}
                  className="input input-sm w-20 text-center"
                  max={1440}
                  min={1}
                  onChange={(event) => setMinutes(event.target.valueAsNumber)}
                  type="number"
                  value={Number.isNaN(minutes) ? '' : minutes}
                />
              ),
            }}
            i18nKey="workspace.moveBy"
          />
        </span>
      </label>
      <button
        className="btn btn-soft btn-sm"
        disabled={delay.isPending || !(minutes > 0)}
        onClick={() => move(1)}
        type="button"
      >
        {t('workspace.later')}
      </button>
      <button
        className="btn btn-ghost btn-sm"
        disabled={delay.isPending || !(minutes > 0)}
        onClick={() => move(-1)}
        type="button"
      >
        {t('workspace.earlier')}
      </button>
    </div>
  );
}

export function ScheduleSection({
  bigScreenPath,
  canManage,
  conflicts,
  matches,
  players,
  stageItemsById,
  teams,
  tournamentId,
}: {
  bigScreenPath: string;
  canManage: boolean;
  /** The matches whose teams or players play elsewhere at the same time. */
  conflicts: OpenApi.ScheduleConflict[];
  matches: FlattenedMatch[];
  players: OpenApi.TournamentPlayer[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teams: OpenApi.TournamentTeamWithPlayers[];
  tournamentId: number;
}) {
  const { t } = useTranslation();
  const conflictsByMatch = groupBy(conflicts, (conflict) => conflict.match_id);
  const participants = {
    players: new Map(players.map((player) => [player.id, player.name])),
    teams: new Map(teams.map((team) => [team.id, team.name])),
  };
  const recalculate = useMutation({
    ...scheduleMatchesApiTournamentsTournamentIdScheduleMatchesPostMutation(),
    meta: { successMessage: t('workspace.timesRecalculated') },
  });
  const upcoming = matches.filter(({ match }) => matchStatus(match) !== 'finished');
  // The latest results are the interesting ones, so finished matches run backwards.
  const finished = matches.filter(({ match }) => matchStatus(match) === 'finished').toReversed();
  const editable = canManage ? tournamentId : undefined;

  return (
    <Surface>
      <SurfaceHeading
        actions={
          <div className="flex flex-wrap gap-2">
            {canManage ? (
              <button
                className="btn btn-soft btn-sm"
                disabled={recalculate.isPending}
                onClick={() => recalculate.mutate({ path: { tournament_id: tournamentId } })}
                type="button"
              >
                {t('workspace.recalculateTimes')}
              </button>
            ) : null}
            <BigScreenLink to={bigScreenPath} />
          </div>
        }
        title={t('tournament.schedule')}
      />
      {canManage ? (
        <>
          <p className="text-sm text-base-content/70">{t('workspace.scheduleHelp')}</p>
          {conflicts.length > 0 ? (
            <p className="alert alert-warning alert-soft text-sm" role="status">
              {t('workspace.conflictsHelp')}
            </p>
          ) : null}
          {upcoming.length > 0 ? <DelayForm tournamentId={tournamentId} /> : null}
        </>
      ) : null}
      {matches.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('schedule.noneScheduled')}</p>
      ) : upcoming.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('schedule.allFinished')}</p>
      ) : (
        <TimeSlots
          conflicts={conflictsByMatch}
          entries={upcoming}
          participants={participants}
          stageItemsById={stageItemsById}
          tournamentId={editable}
        />
      )}
      {finished.length > 0 ? (
        <details
          className="collapse collapse-arrow border border-base-300 bg-base-100/40"
          open={upcoming.length === 0}
        >
          <summary className="collapse-title font-semibold">
            {t('schedule.finishedMatches', { count: finished.length })}
          </summary>
          <div className="collapse-content">
            <TimeSlots
              conflicts={conflictsByMatch}
              entries={finished}
              participants={participants}
              stageItemsById={stageItemsById}
              tournamentId={editable}
            />
          </div>
        </details>
      ) : null}
    </Surface>
  );
}

/** The next two rounds in large print, for a screen at the venue. */
export function BigScreenSchedule({
  matches,
  stageItemsById,
}: {
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
}) {
  const { t } = useTranslation();
  const upcoming = matches.filter(({ match }) => matchStatus(match) !== 'finished');

  return (
    <Surface>
      <SurfaceHeading title={t('tournament.nowAndNext')} />
      {upcoming.length === 0 ? (
        <p className="text-lg text-base-content/80">{t('schedule.allFinished')}</p>
      ) : (
        <TimeSlots entries={upcoming} maxSlots={2} size="lg" stageItemsById={stageItemsById} />
      )}
    </Surface>
  );
}
