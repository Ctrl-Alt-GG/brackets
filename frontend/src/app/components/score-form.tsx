import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useWatch } from 'react-hook-form';

import { useSavedForm } from '../saved-form';

import * as OpenApi from '../../openapi';
import { updateMatchByIdApiTournamentsTournamentIdMatchesMatchIdPutMutation } from '../../openapi/@tanstack/react-query.gen';
import { zMatchBody } from '../../openapi/zod.gen';
import { hasTeam } from '../utils';

type Match = OpenApi.MatchWithDetails | OpenApi.MatchWithDetailsDefinitive;

const scoresSchema = zMatchBody.pick({
  stage_item_input1_score: true,
  stage_item_input2_score: true,
});

/**
 * Where an organizer enters the result of a match.
 *
 * Saving 0-0 means "not played yet", which is also how a wrong result is taken back. A match
 * that really ended 0-0 is recorded with the extra button, where the format allows a draw.
 */
export function ScoreForm({
  allowsDraw,
  label1,
  label2,
  match,
  tournamentId,
}: {
  /** Knockout matches need a winner. */
  allowsDraw: boolean;
  label1: string;
  label2: string;
  match: Match;
  tournamentId: number;
}) {
  const ready = hasTeam(match.stage_item_input1) && hasTeam(match.stage_item_input2);
  const form = useSavedForm({
    resolver: zodResolver(scoresSchema),
    values: {
      stage_item_input1_score: match.stage_item_input1_score,
      stage_item_input2_score: match.stage_item_input2_score,
    },
  });
  const [score1, score2] = useWatch({
    control: form.control,
    name: ['stage_item_input1_score', 'stage_item_input2_score'],
  });
  const save = useMutation({
    ...form.saveCallbacks,
    ...updateMatchByIdApiTournamentsTournamentIdMatchesMatchIdPutMutation(),
    meta: { successMessage: `Score saved: ${label1} vs ${label2}.` },
  });
  const path = { match_id: match.id, tournament_id: tournamentId };
  const timing = {
    custom_duration_minutes: match.custom_duration_minutes,
    custom_margin_minutes: match.custom_margin_minutes,
  };
  const isGoalless = score1 === 0 && score2 === 0;
  const scoreError =
    form.formState.errors.stage_item_input1_score?.message ??
    form.formState.errors.stage_item_input2_score?.message;

  return (
    <form
      className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 rounded-field bg-base-200/60 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]"
      onSubmit={form.handleSubmit((scores) =>
        save.mutate({ body: { ...timing, ...scores, scoreless_result: false }, path }),
      )}
      title={ready ? undefined : 'Waiting for both teams to be known'}
    >
      <span className="truncate text-sm">{label1}</span>
      <input
        aria-label={`${label1} score`}
        className="input input-sm w-16 text-center"
        disabled={!ready || save.isPending}
        max={100000}
        min={0}
        required
        type="number"
        {...form.register('stage_item_input1_score', { valueAsNumber: true })}
      />
      <span className="truncate text-sm">{label2}</span>
      <input
        aria-label={`${label2} score`}
        className="input input-sm w-16 text-center"
        disabled={!ready || save.isPending}
        max={100000}
        min={0}
        required
        type="number"
        {...form.register('stage_item_input2_score', { valueAsNumber: true })}
      />
      {/* Below the scores on narrow screens, next to them otherwise. */}
      <button
        className="btn btn-soft btn-sm col-span-2 sm:col-span-1 sm:col-start-3 sm:row-span-2 sm:row-start-1"
        disabled={!ready || save.isPending}
        type="submit"
      >
        {save.isPending ? 'Saving…' : 'Save'}
      </button>
      {scoreError ? (
        <p className="col-span-2 text-xs text-error sm:col-span-3" role="alert">
          {scoreError}
        </p>
      ) : null}
      {ready && allowsDraw && isGoalless ? (
        <p className="col-span-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/70 sm:col-span-3">
          {match.scoreless_result ? (
            'Recorded as a 0–0 draw. Save 0–0 to mark it as not played.'
          ) : (
            <>
              0–0 means not played yet.
              <button
                className="link"
                disabled={save.isPending}
                onClick={() =>
                  save.mutate({
                    body: {
                      ...timing,
                      scoreless_result: true,
                      stage_item_input1_score: 0,
                      stage_item_input2_score: 0,
                    },
                    path,
                  })
                }
                type="button"
              >
                It ended 0–0
              </button>
            </>
          )}
        </p>
      ) : null}
    </form>
  );
}
