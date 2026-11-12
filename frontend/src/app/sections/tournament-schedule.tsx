import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  delayScheduleApiTournamentsTournamentIdDelaySchedulePostMutation,
  scheduleMatchesApiTournamentsTournamentIdScheduleMatchesPostMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { MatchCard } from '../components/match-card';
import { MatchScoreEditor } from '../components/match-score-editor';
import type { FlattenedMatch } from '../types';
import { cx, formatMatchTime, groupBy, matchStatus } from '../utils';
import { Surface, SurfaceHeading } from '../ui';

/** Matches sorted by time, grouped under the time they start. */
function TimeSlots({
  entries,
  maxSlots,
  size = 'md',
  stageItemsById,
  tournamentId,
}: {
  entries: FlattenedMatch[];
  maxSlots?: number;
  size?: 'lg' | 'md';
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  /** Set for organizers, who enter the results on the matches. */
  tournamentId?: number;
}) {
  const slots = groupBy(entries, (entry) => entry.match.start_time ?? '');

  return (
    <div className="space-y-6">
      {[...slots.entries()].slice(0, maxSlots).map(([startTime, slotEntries]) => (
        <section className="space-y-3" key={startTime || 'unscheduled'}>
          <h3 className={cx('font-display font-semibold', size === 'lg' ? 'text-3xl' : 'text-xl')}>
            {formatMatchTime(startTime || null)}
          </h3>
          <div
            className={cx(
              'grid gap-3',
              size === 'lg' ? 'xl:grid-cols-2' : 'md:grid-cols-2 xl:grid-cols-3',
            )}
          >
            {slotEntries.map((entry) => (
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
                showTime={false}
                size={size}
                stageItemsById={stageItemsById}
              />
            ))}
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
  const [minutes, setMinutes] = useState(15);
  const delay = useMutation({
    ...delayScheduleApiTournamentsTournamentIdDelaySchedulePostMutation(),
    meta: { successMessage: 'Schedule moved.' },
  });
  const move = (sign: 1 | -1) =>
    delay.mutate({ body: { minutes: sign * minutes }, path: { tournament_id: tournamentId } });

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-box border border-base-300 bg-base-100/40 p-4">
      <label className="fieldset p-0">
        <span className="fieldset-legend">Running late?</span>
        <span className="flex items-center gap-2 text-sm">
          Move the rounds that are still to come by
          <input
            aria-label="Minutes to move the schedule by"
            className="input input-sm w-20 text-center"
            max={1440}
            min={1}
            onChange={(event) => setMinutes(event.target.valueAsNumber)}
            type="number"
            value={Number.isNaN(minutes) ? '' : minutes}
          />
          minutes
        </span>
      </label>
      <button
        className="btn btn-soft btn-sm"
        disabled={delay.isPending || !(minutes > 0)}
        onClick={() => move(1)}
        type="button"
      >
        Later
      </button>
      <button
        className="btn btn-ghost btn-sm"
        disabled={delay.isPending || !(minutes > 0)}
        onClick={() => move(-1)}
        type="button"
      >
        Earlier
      </button>
    </div>
  );
}

export function ScheduleSection({
  bigScreenPath,
  canManage,
  matches,
  stageItemsById,
  tournamentId,
}: {
  bigScreenPath: string;
  canManage: boolean;
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  tournamentId: number;
}) {
  const recalculate = useMutation({
    ...scheduleMatchesApiTournamentsTournamentIdScheduleMatchesPostMutation(),
    meta: { successMessage: 'Match times recalculated.' },
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
                Recalculate times
              </button>
            ) : null}
            <Link className="btn btn-ghost btn-sm" to={bigScreenPath}>
              Big screen
            </Link>
          </div>
        }
        title="Schedule"
      />
      {canManage ? (
        <>
          <p className="text-sm text-base-content/70">
            Match times are planned automatically: all matches of a round start together, and a
            round starts when the previous one has finished. Enter results right here on the
            matches. The planned times follow from the start time, match duration and break in
            Settings, and the match duration of a stage in Stages.
          </p>
          {upcoming.length > 0 ? <DelayForm tournamentId={tournamentId} /> : null}
        </>
      ) : null}
      {matches.length === 0 ? (
        <p className="text-sm text-base-content/70">No matches have been scheduled yet.</p>
      ) : upcoming.length === 0 ? (
        <p className="text-sm text-base-content/70">All matches are finished.</p>
      ) : (
        <TimeSlots entries={upcoming} stageItemsById={stageItemsById} tournamentId={editable} />
      )}
      {finished.length > 0 ? (
        <details
          className="collapse collapse-arrow border border-base-300 bg-base-100/40"
          open={upcoming.length === 0}
        >
          <summary className="collapse-title font-semibold">
            Finished matches ({finished.length})
          </summary>
          <div className="collapse-content">
            <TimeSlots entries={finished} stageItemsById={stageItemsById} tournamentId={editable} />
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
  const upcoming = matches.filter(({ match }) => matchStatus(match) !== 'finished');

  return (
    <Surface>
      <SurfaceHeading title="Now and next" />
      {upcoming.length === 0 ? (
        <p className="text-lg text-base-content/80">All matches are finished.</p>
      ) : (
        <TimeSlots entries={upcoming} maxSlots={2} size="lg" stageItemsById={stageItemsById} />
      )}
    </Surface>
  );
}
