import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useWatch } from 'react-hook-form';

import { useSavedForm } from '../saved-form';
import * as OpenApi from '../../openapi';
import {
  activateNextStageApiTournamentsTournamentIdStagesActivatePostMutation,
  createStageApiTournamentsTournamentIdStagesPostMutation,
  createStageItemApiTournamentsTournamentIdStageItemsPostMutation,
  deleteStageApiTournamentsTournamentIdStagesStageIdDeleteMutation,
  deleteStageItemApiTournamentsTournamentIdStageItemsStageItemIdDeleteMutation,
  updateStageApiTournamentsTournamentIdStagesStageIdPutMutation,
  updateStageItemApiTournamentsTournamentIdStageItemsStageItemIdPutMutation,
} from '../../openapi/@tanstack/react-query.gen';
import {
  zStageItemCreateBody,
  zStageItemUpdateBody,
  zStageUpdateBody,
} from '../../openapi/zod.gen';
import { useCreateForm } from '../create-form';
import { confirm } from '../confirm';
import { StageItemRounds, stageItemStatus } from './stage-item-rounds';
import { StageItemSlots } from './stage-item-slots';
import { StageItemVisualization } from './tournament-overview';
import type { TournamentBundle } from '../types';
import { formatPoints } from '../format';
import { isScored } from '../matches';
import { cx } from '../utils';
import { Disclosure, Field, Surface, SurfaceHeading } from '../ui';

function StageForm({
  stage,
  tournament,
}: {
  stage: OpenApi.StageWithStageItems;
  tournament: OpenApi.Tournament;
}) {
  const form = useSavedForm({
    resolver: zodResolver(zStageUpdateBody),
    values: { custom_duration_minutes: stage.custom_duration_minutes, name: stage.name },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateStageApiTournamentsTournamentIdStagesStageIdPutMutation(),
    meta: { successMessage: 'Stage saved.' },
  });
  const remove = useMutation({
    ...deleteStageApiTournamentsTournamentIdStagesStageIdDeleteMutation(),
    meta: { successMessage: 'Stage deleted.' },
  });
  const path = { stage_id: stage.id, tournament_id: tournament.id };

  return (
    <form
      className="grid items-end gap-x-4 md:grid-cols-[1fr_1fr_auto_auto]"
      onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
    >
      <Field error={form.formState.errors.name?.message} label="Stage name">
        <input className="input w-full" {...form.register('name')} />
      </Field>
      <Field
        error={form.formState.errors.custom_duration_minutes?.message}
        label="Match duration (minutes)"
      >
        <input
          className="input w-full"
          min={1}
          placeholder={`Tournament default (${tournament.duration_minutes})`}
          type="number"
          {...form.register('custom_duration_minutes', {
            setValueAs: (value) => (value === '' || value == null ? null : Number(value)),
          })}
        />
      </Field>
      <button className="btn btn-primary mb-1" disabled={update.isPending} type="submit">
        Save stage
      </button>
      <button
        className="btn btn-error btn-soft mb-1"
        disabled={remove.isPending}
        onClick={async () => {
          if (
            await confirm({
              confirmLabel: 'Delete stage',
              destructive: true,
              message: `Delete stage ${stage.name}?`,
            })
          ) {
            remove.mutate({ path });
          }
        }}
        type="button"
      >
        Delete stage
      </button>
    </form>
  );
}

// A bracket halves every round, so it starts from a power of two.
const SINGLE_ELIMINATION_TEAM_COUNTS = [2, 4, 8, 16, 32];

const newStageItemSchema = zStageItemCreateBody.refine(
  (body) =>
    body.type !== 'SINGLE_ELIMINATION' || SINGLE_ELIMINATION_TEAM_COUNTS.includes(body.team_count),
  {
    message: `A single elimination bracket has ${SINGLE_ELIMINATION_TEAM_COUNTS.join(', ')} teams`,
    path: ['team_count'],
  },
);

/** The bracket size closest to the number of teams the organizer had in mind. */
function nearestBracketSize(teamCount: number) {
  return SINGLE_ELIMINATION_TEAM_COUNTS.reduce((nearest, count) =>
    Math.abs(count - teamCount) < Math.abs(nearest - teamCount) ? count : nearest,
  );
}

function NewStageItemForm({
  rankings,
  stageId,
  tournamentId,
}: {
  rankings: OpenApi.Ranking[];
  stageId: number;
  tournamentId: number;
}) {
  const form = useCreateForm({
    defaultValues: {
      name: '',
      ranking_id: rankings[0]?.id ?? null,
      stage_id: stageId,
      team_count: 8,
      type: 'ROUND_ROBIN' as const,
    },
    resolver: zodResolver(newStageItemSchema),
  });
  const create = useMutation({
    ...createStageItemApiTournamentsTournamentIdStageItemsPostMutation(),
    meta: { successMessage: 'Stage item created.' },
  });
  const type = useWatch({ control: form.control, name: 'type' });

  return (
    <form
      className="grid items-end gap-x-4 rounded-box border border-base-300 bg-base-100/40 p-4 md:grid-cols-4"
      onSubmit={form.submitWith((body) =>
        create.mutateAsync({
          body: { ...body, name: body.name?.trim() || null },
          path: { tournament_id: tournamentId },
        }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field label="Name">
          <input className="input w-full" placeholder="Upper bracket" {...form.register('name')} />
        </Field>
        <Field label="Type">
          <select
            className="select w-full"
            {...form.register('type', {
              // The bracket's sizes are the only choices then, so the count becomes one of them.
              onChange: (event: { target: { value: string } }) => {
                if (event.target.value === 'SINGLE_ELIMINATION') {
                  form.setValue('team_count', nearestBracketSize(form.getValues('team_count')), {
                    shouldValidate: true,
                  });
                }
              },
            })}
          >
            <option value="ROUND_ROBIN">Round robin</option>
            <option value="SINGLE_ELIMINATION">Single elimination</option>
            <option value="SWISS">Swiss</option>
          </select>
        </Field>
        <Field error={form.formState.errors.team_count?.message} label="Team count">
          {type === 'SINGLE_ELIMINATION' ? (
            <select
              className="select w-full"
              {...form.register('team_count', { valueAsNumber: true })}
            >
              {SINGLE_ELIMINATION_TEAM_COUNTS.map((count) => (
                <option key={count} value={count}>
                  {count}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="input w-full"
              max={64}
              min={2}
              required
              type="number"
              {...form.register('team_count', { valueAsNumber: true })}
            />
          )}
        </Field>
        {rankings.length > 1 ? (
          <Field label="Ranking">
            <select
              className="select w-full"
              {...form.register('ranking_id', { valueAsNumber: true })}
            >
              {rankings.map((ranking) => (
                <option key={ranking.id} value={ranking.id}>
                  #{ranking.position}: win {formatPoints(ranking.win_points)}, draw{' '}
                  {formatPoints(ranking.draw_points)}, loss {formatPoints(ranking.loss_points)}
                </option>
              ))}
            </select>
          </Field>
        ) : null}
        <div className="md:col-span-4">
          <button className="btn btn-primary mt-3" type="submit">
            Create stage item
          </button>
        </div>
      </fieldset>
    </form>
  );
}

function StageItemNameForm({
  fedStageItems,
  stageItem,
  tournamentId,
}: {
  /** The stage items with a slot that takes a team from this one. */
  fedStageItems: OpenApi.StageItemWithRounds[];
  stageItem: OpenApi.StageItemWithRounds;
  tournamentId: number;
}) {
  const form = useSavedForm({
    resolver: zodResolver(zStageItemUpdateBody),
    values: { name: stageItem.name },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateStageItemApiTournamentsTournamentIdStageItemsStageItemIdPutMutation(),
    meta: { successMessage: 'Name saved.' },
  });
  const remove = useMutation({
    ...deleteStageItemApiTournamentsTournamentIdStageItemsStageItemIdDeleteMutation(),
    meta: { successMessage: 'Stage item deleted.' },
  });
  const path = { stage_item_id: stageItem.id, tournament_id: tournamentId };

  return (
    <form
      className="flex flex-col gap-2 md:flex-row"
      onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}
    >
      <input
        aria-label="Stage item name"
        className="input w-full"
        placeholder="Stage item name"
        {...form.register('name')}
      />
      <button className="btn btn-primary" disabled={update.isPending} type="submit">
        Save name
      </button>
      <button
        className="btn btn-error btn-soft"
        disabled={remove.isPending}
        onClick={async () => {
          const fed = fedStageItems.map((item) => item.name || item.type_name).join(', ');
          const consequence = fed
            ? ` The slots of ${fed} that take a team from it become open.`
            : '';
          if (
            await confirm({
              confirmLabel: 'Delete stage item',
              destructive: true,
              message: `Delete stage item ${stageItem.name || stageItem.type_name} with its matches and results?${consequence}`,
            })
          ) {
            remove.mutate({ path });
          }
        }}
        type="button"
      >
        Delete item
      </button>
    </form>
  );
}

export function StagesSection({
  bundle,
  focusStageItem,
}: {
  bundle: TournamentBundle;
  focusStageItem: OpenApi.StageItemWithRounds | null;
}) {
  const teamLookup = new Map(bundle.teams.map((team) => [team.id, team] as const));
  const rankings = bundle.rankings.toSorted((left, right) => left.position - right.position);
  const stageItemsById = new Map(
    bundle.stages.flatMap((stage) => stage.stage_items.map((item) => [item.id, item] as const)),
  );
  const path = { tournament_id: bundle.tournament.id };
  const createStage = useMutation({
    ...createStageApiTournamentsTournamentIdStagesPostMutation(),
    meta: { successMessage: 'Stage created.' },
  });
  const activateNext = useMutation({
    ...activateNextStageApiTournamentsTournamentIdStagesActivatePostMutation(),
    meta: { successMessage: 'Moved active stage forward.' },
  });
  const activatePrevious = useMutation({
    ...activateNextStageApiTournamentsTournamentIdStagesActivatePostMutation(),
    meta: { successMessage: 'Moved active stage backward.' },
  });

  // Stages come in the order they were added, which is the order they are played in.
  const activeIndex = bundle.stages.findIndex((stage) => stage.is_active);
  const activeStage = activeIndex >= 0 ? bundle.stages[activeIndex] : undefined;
  // Before the first stage is activated, "next" starts it, and there is nothing to go back to.
  const hasNextStage = activeIndex < bundle.stages.length - 1;
  const hasPreviousStage = activeIndex > 0;
  const activeMatches = (activeStage?.stage_items ?? []).flatMap((stageItem) =>
    stageItem.rounds.flatMap((round) => round.matches),
  );
  const results = activeMatches.filter(isScored).length;
  const withoutResult = activeMatches.length - results;
  // Places that only seeding decided, because the teams are level on every criterion.
  const seedingDecides = Object.values(bundle.nextStageRankings)
    .flat()
    .flatMap((entry) => (entry.tied_team ? [{ team: entry.team, tiedTeam: entry.tied_team }] : []));

  const goForward = async () => {
    const reasons = [
      // Teams move on by the standings as they are, which an unplayed match would still change.
      ...(activeStage != null && withoutResult > 0
        ? [
            `${withoutResult} ${withoutResult === 1 ? 'match' : 'matches'} of ${activeStage.name} ${withoutResult === 1 ? 'has' : 'have'} no result yet. Teams move on by the standings as they are now.`,
          ]
        : []),
      ...seedingDecides.map(
        ({ team, tiedTeam }) =>
          `${team.name} and ${tiedTeam.name} are level on every criterion: only seeding puts ${team.name} ahead.`,
      ),
    ];
    if (
      reasons.length > 0 &&
      !(await confirm({
        confirmLabel: 'Activate next stage',
        message: (
          <>
            {reasons.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
            <p>Activate the next stage anyway?</p>
          </>
        ),
      }))
    ) {
      return;
    }
    activateNext.mutate({ body: { direction: 'next', discard_results: false }, path });
  };

  const goBack = async () => {
    // Going back releases the teams that advanced, and their results in this stage with them.
    if (
      activeStage != null &&
      results > 0 &&
      !(await confirm({
        confirmLabel: 'Go back',
        destructive: true,
        message: `Going back discards the ${results} ${results === 1 ? 'result' : 'results'} of ${activeStage.name}. This cannot be undone. Go back to the previous stage?`,
      }))
    ) {
      return;
    }
    activatePrevious.mutate({
      body: { direction: 'previous', discard_results: results > 0 },
      path,
    });
  };

  return (
    <div className="space-y-6">
      <Surface>
        <SurfaceHeading
          actions={
            <div className="flex flex-wrap gap-2">
              <button
                className="btn btn-primary btn-sm"
                disabled={createStage.isPending}
                onClick={() => createStage.mutate({ path })}
                type="button"
              >
                Add stage
              </button>
              <button
                className="btn btn-soft btn-sm"
                disabled={!hasNextStage || activateNext.isPending}
                onClick={() => void goForward()}
                type="button"
              >
                Activate next stage
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={!hasPreviousStage || activatePrevious.isPending}
                onClick={() => void goBack()}
                type="button"
              >
                Activate previous stage
              </button>
            </div>
          }
          title="Bracket editor"
        />
        <p className="text-sm text-base-content/70">
          A tournament is played stage by stage. Activating the next stage moves the teams on by the
          standings of the current one.
        </p>
      </Surface>
      {bundle.stages.map((stage) => (
        <Disclosure
          className="collapse collapse-arrow border border-base-300 bg-base-200/60"
          key={stage.id}
          open={stage.is_active || stage.stage_items.some((item) => item.id === focusStageItem?.id)}
          summary={
            <>
              <span className="flex flex-wrap items-center gap-2">
                <span
                  className={cx(
                    'badge badge-soft badge-sm',
                    stage.is_active ? 'badge-accent' : null,
                  )}
                >
                  {stage.is_active ? 'Active' : 'Inactive'}
                </span>
                <span className="text-sm text-base-content/70">
                  {stage.stage_items.length} stage items
                </span>
              </span>
              <span className="mt-2 block font-display text-2xl font-semibold">{stage.name}</span>
            </>
          }
        >
          <div className="collapse-content space-y-5">
            <StageForm stage={stage} tournament={bundle.tournament} />
            <NewStageItemForm
              rankings={rankings}
              stageId={stage.id}
              tournamentId={bundle.tournament.id}
            />
            {stage.stage_items.map((stageItem) => (
              <details
                className="collapse collapse-arrow border border-base-300 bg-base-100/50"
                key={stageItem.id}
                open
              >
                <summary className="collapse-title">
                  <span className="badge badge-soft badge-sm">{stageItem.type_name}</span>
                  <span className="mt-2 block text-xl font-semibold">
                    {stageItem.name || stageItem.type_name}
                  </span>
                  <span className="mt-1 block text-sm text-base-content/70">
                    {stageItemStatus(stageItem)}
                  </span>
                </summary>
                <div className="collapse-content space-y-5">
                  <StageItemNameForm
                    fedStageItems={[...stageItemsById.values()].filter((other) =>
                      other.inputs.some(
                        (input) => input.winner_from_stage_item_id === stageItem.id,
                      ),
                    )}
                    stageItem={stageItem}
                    tournamentId={bundle.tournament.id}
                  />
                  <StageItemSlots
                    nextStageEntries={bundle.nextStageRankings[String(stageItem.id)]}
                    options={bundle.availableInputs[String(stage.id)] ?? []}
                    stageItem={stageItem}
                    stageItemsById={stageItemsById}
                    teamLookup={teamLookup}
                    tournamentId={bundle.tournament.id}
                  />
                  <section className="space-y-4 rounded-box border border-base-300 bg-base-200/60 p-4">
                    <h5 className="font-semibold">Rounds</h5>
                    <StageItemRounds
                      stageItem={stageItem}
                      stageItemsById={stageItemsById}
                      tournamentId={bundle.tournament.id}
                    />
                  </section>
                  <StageItemVisualization
                    showMatches={false}
                    stageItem={stageItem}
                    stageItemsById={stageItemsById}
                    standings={bundle.standings}
                    teamMap={teamLookup}
                    tournamentId={bundle.tournament.id}
                  />
                </div>
              </details>
            ))}
          </div>
        </Disclosure>
      ))}
    </div>
  );
}
