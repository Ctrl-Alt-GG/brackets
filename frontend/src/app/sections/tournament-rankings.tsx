import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { z } from 'zod';

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
import { useOrganizerTranslation } from '../organizer-locales';
import { CheckboxField, Disclosure, Field, SaveButton, Surface, SurfaceHeading } from '../ui';

// The page numbers the rules from 1, the API from 0.
const rankingFormSchema = zRankingBody.extend({
  position: z
    .number()
    .int()
    .min(1)
    .transform((position) => position - 1),
});

const POINT_FIELDS = [
  ['win_points', 'rankings.winPoints'],
  ['draw_points', 'rankings.drawPoints'],
  ['loss_points', 'rankings.lossPoints'],
] as const;

function NewRankingForm({ tournamentId }: { tournamentId: number }) {
  const { t } = useOrganizerTranslation();
  const form = useCreateForm({
    defaultValues: { add_score_points: false, draw_points: 1, loss_points: 0, win_points: 3 },
    resolver: zodResolver(zRankingCreateBody),
  });
  const create = useMutation({
    ...createRankingApiTournamentsTournamentIdRankingsPostMutation(),
    meta: { successMessage: t('rankings.created') },
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
            <Field error={form.formState.errors[name]?.message} key={name} label={t(label)}>
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
          description={t('rankings.addScoresDescription')}
          label={t('rankings.addScores')}
          {...form.register('add_score_points')}
        />
        <button className="btn btn-primary mt-4" type="submit">
          {t('rankings.create')}
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
  const { t } = useOrganizerTranslation();
  return (
    <Disclosure
      className="collapse collapse-arrow border border-base-300 bg-base-100/50"
      summary={
        <>
          <span className="flex flex-wrap items-center gap-2 font-semibold">
            {t('rankings.name', { position: ranking.position + 1 })}
            {ranking.add_score_points ? (
              <span className="badge badge-soft badge-accent badge-sm">
                {t('rankings.addsScores')}
              </span>
            ) : null}
          </span>
          <span className="block text-sm text-base-content/70">
            {t('rankings.summary', {
              draw: formatPoints(ranking.draw_points),
              loss: formatPoints(ranking.loss_points),
              win: formatPoints(ranking.win_points),
            })}
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
  const { t } = useOrganizerTranslation();
  const form = useSavedForm({
    resolver: zodResolver(rankingFormSchema),
    // Follows the saved ranking, without throwing away what the organizer is typing. The API
    // sends points as decimal text and the inputs hold numbers, so the saved ranking is compared
    // as numbers too: otherwise an untouched field would look edited and keep an old value.
    values: {
      add_score_points: ranking.add_score_points,
      draw_points: Number(ranking.draw_points),
      loss_points: Number(ranking.loss_points),
      position: ranking.position + 1,
      win_points: Number(ranking.win_points),
    },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateRankingByIdApiTournamentsTournamentIdRankingsRankingIdPutMutation(),
    meta: { successMessage: t('rankings.saved') },
  });
  const remove = useMutation({
    ...deleteRankingApiTournamentsTournamentIdRankingsRankingIdDeleteMutation(),
    meta: { successMessage: t('rankings.deleted') },
  });
  const path = { ranking_id: ranking.id, tournament_id: tournamentId };
  const { errors } = form.formState;

  return (
    <form
      className="collapse-content"
      onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
    >
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field error={errors.position?.message} label={t('rankings.position')}>
          <input
            className="input w-full"
            min={1}
            required
            type="number"
            {...form.register('position', { valueAsNumber: true })}
          />
        </Field>
        {POINT_FIELDS.map(([name, label]) => (
          <Field error={errors[name]?.message} key={name} label={t(label)}>
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
        description={t('rankings.addScoresDescription')}
        label={t('rankings.addScores')}
        {...form.register('add_score_points')}
      />
      <div className="mt-4 flex flex-wrap gap-2">
        <SaveButton dirty={form.formState.isDirty} disabled={update.isPending}>
          {t('rankings.save')}
        </SaveButton>
        <button
          className="btn btn-error btn-soft"
          disabled={remove.isPending}
          onClick={async () => {
            if (
              await confirm({
                confirmLabel: t('rankings.delete'),
                destructive: true,
                message: t('rankings.deleteQuestion', { position: ranking.position + 1 }),
              })
            ) {
              remove.mutate({ path });
            }
          }}
          type="button"
        >
          {t('rankings.delete')}
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
  teamMap: Map<number, OpenApi.TournamentTeamWithPlayers>;
}) {
  const { t } = useOrganizerTranslation();
  return (
    <div className="space-y-6">
      <StandingsSection
        rankings={bundle.rankings}
        stages={bundle.stages}
        standings={bundle.standings}
        teamMap={teamMap}
      />
      <div className="grid items-start gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Surface>
          <SurfaceHeading
            actions={
              <span className="text-sm text-base-content/70">
                {t('rankings.count', { count: bundle.rankings.length })}
              </span>
            }
            title={t('rankings.definitions')}
          />
          <p className="text-sm text-base-content/70">{t('rankings.help')}</p>
          <div className="space-y-3">
            {bundle.rankings
              .toSorted((left, right) => left.position - right.position)
              .map((ranking) => (
                <RankingEditor
                  key={ranking.id}
                  ranking={ranking}
                  tournamentId={bundle.tournament.id}
                />
              ))}
          </div>
        </Surface>
        <Surface>
          <SurfaceHeading title={t('rankings.rule')} />
          <NewRankingForm tournamentId={bundle.tournament.id} />
        </Surface>
      </div>
    </div>
  );
}
