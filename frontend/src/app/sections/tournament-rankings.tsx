import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';

import { useSavedForm } from '../saved-form';
import * as OpenApi from '../../openapi';
import {
  createRankingApiTournamentsTournamentIdRankingsPostMutation,
  deleteRankingApiTournamentsTournamentIdRankingsRankingIdDeleteMutation,
  updateRankingByIdApiTournamentsTournamentIdRankingsRankingIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import { zRankingBody, zRankingCreateBody } from '../../openapi/zod.gen';
import { useCreateForm } from '../create-form';
import { confirm } from '../confirm';
import { StandingsSection } from './tournament-standings';
import type { TournamentBundle } from '../types';
import { formatPoints } from '../format';
import { CheckboxField, Disclosure, Field, Surface, SurfaceHeading } from '../ui';

const ADD_SCORE_POINTS_DESCRIPTION =
  'Teams also get their score in each match added to their points.';

const POINT_FIELDS = [
  ['win_points', 'Win points'],
  ['draw_points', 'Draw points'],
  ['loss_points', 'Loss points'],
] as const;

function NewRankingForm({ tournamentId }: { tournamentId: number }) {
  const form = useCreateForm({
    defaultValues: { add_score_points: false, draw_points: 1, loss_points: 0, win_points: 3 },
    resolver: zodResolver(zRankingCreateBody),
  });
  const create = useMutation({
    ...createRankingApiTournamentsTournamentIdRankingsPostMutation(),
    meta: { successMessage: 'Ranking created.' },
  });

  return (
    <form
      onSubmit={form.submitWith((body) =>
        create.mutateAsync({ body, path: { tournament_id: tournamentId } }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <div className="grid gap-x-4 md:grid-cols-3">
          {POINT_FIELDS.map(([name, label]) => (
            <Field error={form.formState.errors[name]?.message} key={name} label={label}>
              <input
                className="input w-full"
                required
                step="any"
                type="number"
                {...form.register(name, { valueAsNumber: true })}
              />
            </Field>
          ))}
        </div>
        <CheckboxField
          className="mt-3"
          description={ADD_SCORE_POINTS_DESCRIPTION}
          label="Add raw score points"
          {...form.register('add_score_points')}
        />
        <button className="btn btn-primary mt-4" type="submit">
          Create ranking
        </button>
      </fieldset>
    </form>
  );
}

function RankingEditor({
  ranking,
  tournamentId,
}: {
  ranking: OpenApi.Ranking;
  tournamentId: number;
}) {
  return (
    <Disclosure
      className="collapse collapse-arrow border border-base-300 bg-base-100/50"
      summary={
        <>
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            Ranking #{ranking.position}
            {ranking.add_score_points ? (
              <span className="badge badge-soft badge-accent badge-sm">Adds match scores</span>
            ) : null}
          </span>
          <span className="block text-sm text-base-content/70">
            Win {formatPoints(ranking.win_points)} · Draw {formatPoints(ranking.draw_points)} · Loss{' '}
            {formatPoints(ranking.loss_points)}
          </span>
        </>
      }
    >
      <RankingForm ranking={ranking} tournamentId={tournamentId} />
    </Disclosure>
  );
}

function RankingForm({
  ranking,
  tournamentId,
}: {
  ranking: OpenApi.Ranking;
  tournamentId: number;
}) {
  const form = useSavedForm({
    resolver: zodResolver(zRankingBody),
    // Follows the saved ranking, without throwing away what the organizer is typing. The API
    // sends points as decimal text and the inputs hold numbers, so the saved ranking is compared
    // as numbers too: otherwise an untouched field would look edited and keep an old value.
    values: {
      add_score_points: ranking.add_score_points,
      draw_points: Number(ranking.draw_points),
      loss_points: Number(ranking.loss_points),
      position: ranking.position,
      win_points: Number(ranking.win_points),
    },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateRankingByIdApiTournamentsTournamentIdRankingsRankingIdPutMutation(),
    meta: { successMessage: 'Ranking saved.' },
  });
  const remove = useMutation({
    ...deleteRankingApiTournamentsTournamentIdRankingsRankingIdDeleteMutation(),
    meta: { successMessage: 'Ranking deleted.' },
  });
  const path = { ranking_id: ranking.id, tournament_id: tournamentId };
  const { errors } = form.formState;

  return (
    <form
      className="collapse-content"
      onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
    >
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field error={errors.position?.message} label="Position">
          <input
            className="input w-full"
            min={0}
            required
            type="number"
            {...form.register('position', { valueAsNumber: true })}
          />
        </Field>
        {POINT_FIELDS.map(([name, label]) => (
          <Field error={errors[name]?.message} key={name} label={label}>
            <input
              className="input w-full"
              required
              step="any"
              type="number"
              {...form.register(name, { valueAsNumber: true })}
            />
          </Field>
        ))}
      </div>
      <CheckboxField
        className="mt-3"
        description={ADD_SCORE_POINTS_DESCRIPTION}
        label="Add raw score points"
        {...form.register('add_score_points')}
      />
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn btn-primary" disabled={update.isPending} type="submit">
          Save ranking
        </button>
        <button
          className="btn btn-error btn-soft"
          disabled={remove.isPending}
          onClick={async () => {
            if (
              await confirm({
                confirmLabel: 'Delete ranking',
                destructive: true,
                message: `Delete ranking #${ranking.position}?`,
              })
            ) {
              remove.mutate({ path });
            }
          }}
          type="button"
        >
          Delete ranking
        </button>
      </div>
    </form>
  );
}

export function RankingsSection({
  bundle,
  teamMap,
}: {
  bundle: TournamentBundle;
  teamMap: Map<number, OpenApi.FullTeamWithPlayers>;
}) {
  return (
    <div className="space-y-6">
      <StandingsSection
        rankings={bundle.rankings}
        stages={bundle.stages}
        standings={bundle.standings}
        teamMap={teamMap}
      />
      <div className="grid items-start gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <Surface>
          <SurfaceHeading title="Ranking rule" />
          <NewRankingForm tournamentId={bundle.tournament.id} />
        </Surface>
        <Surface>
          <SurfaceHeading
            actions={
              <span className="text-sm text-base-content/70">
                {bundle.rankings.length} rankings
              </span>
            }
            title="Ranking definitions"
          />
          <div className="space-y-3">
            {bundle.rankings.map((ranking) => (
              <RankingEditor
                key={ranking.id}
                ranking={ranking}
                tournamentId={bundle.tournament.id}
              />
            ))}
          </div>
        </Surface>
      </div>
    </div>
  );
}
