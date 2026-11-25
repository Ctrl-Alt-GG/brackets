import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';

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
import type { TournamentBundle } from '../types';
import { formatPoints, pointsPhrase } from '../format';
import {
  inputLabel,
  isBracket,
  isScored,
  stageItemName,
  stageItemStandings,
  stageName,
  stageTypeName,
} from '../matches';
import { toBracketViewerData } from '../bracket-adapter';
import { BracketViewer } from '../components/bracket-viewer';
import { TeamLink } from '../components/team-link';
import { organizerT, useOrganizerTranslation } from '../organizer-locales';
import { cx } from '../utils';
import { Disclosure, Field, SaveButton, Surface, SurfaceHeading } from '../ui';

function StageForm({
  stage,
  tournament,
}: {
  stage: OpenApi.StageWithStageItems;
  tournament: OpenApi.Tournament;
}) {
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  // A stage the site named is shown with that name in the page's language. It keeps its stored
  // name unless the organizer types another one.
  const shownName = stageName(stage, shared);
  const form = useSavedForm({
    resolver: zodResolver(zStageUpdateBody),
    values: { custom_duration_minutes: stage.custom_duration_minutes, name: shownName },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateStageApiTournamentsTournamentIdStagesStageIdPutMutation(),
    meta: { successMessage: t('stages.saved') },
  });
  const remove = useMutation({
    ...deleteStageApiTournamentsTournamentIdStagesStageIdDeleteMutation(),
    meta: { successMessage: t('stages.deleted') },
  });
  const path = { stage_id: stage.id, tournament_id: tournament.id };

  return (
    <form
      className="grid items-end gap-x-4 md:grid-cols-[1fr_1fr_auto_auto]"
      onSubmit={form.handleSubmit((body) =>
        update.mutate({
          body: { ...body, name: body.name === shownName ? stage.name : body.name },
          path,
        }),
      )}
    >
      <Field error={form.formState.errors.name?.message} label={t('stages.stageName')}>
        <input className="input w-full" {...form.register('name')} />
      </Field>
      <Field
        error={form.formState.errors.custom_duration_minutes?.message}
        label={t('common.matchDuration')}
      >
        <input
          className="input w-full"
          min={1}
          placeholder={t('stages.tournamentDefault', { minutes: tournament.duration_minutes })}
          type="number"
          {...form.register('custom_duration_minutes', {
            setValueAs: (value) => (value === '' || value == null ? null : Number(value)),
          })}
        />
      </Field>
      <SaveButton className="mb-1" dirty={form.formState.isDirty} disabled={update.isPending}>
        {t('stages.save')}
      </SaveButton>
      <button
        className="btn btn-error btn-soft mb-1"
        disabled={remove.isPending}
        onClick={async () => {
          if (
            await confirm({
              confirmLabel: t('stages.delete'),
              destructive: true,
              message: t('stages.deleteQuestion', { name: shownName }),
            })
          ) {
            remove.mutate({ path });
          }
        }}
        type="button"
      >
        {t('stages.delete')}
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
    error: () =>
      organizerT('validation.bracketSizes', { counts: SINGLE_ELIMINATION_TEAM_COUNTS.join(', ') }),
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
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
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
    meta: { successMessage: t('stages.itemCreated') },
  });
  const type = useWatch({ control: form.control, name: 'type' });

  return (
    <form
      className="collapse-content grid items-end gap-x-4 md:grid-cols-4"
      onSubmit={form.submitWith((body) =>
        create.mutateAsync({
          body: { ...body, name: body.name?.trim() || null },
          path: { tournament_id: tournamentId },
        }),
      )}
    >
      <fieldset className="contents" disabled={form.locked}>
        <Field label={t('common.name')}>
          <input
            className="input w-full"
            placeholder={t('stages.namePlaceholder')}
            {...form.register('name')}
          />
        </Field>
        <Field label={t('stages.type')}>
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
            {(['ROUND_ROBIN', 'SINGLE_ELIMINATION', 'SWISS'] as const).map((stageType) => (
              <option key={stageType} value={stageType}>
                {stageTypeName({ type: stageType }, shared)}
              </option>
            ))}
          </select>
        </Field>
        <Field error={form.formState.errors.team_count?.message} label={t('stages.teamCount')}>
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
          <Field label={t('stages.ranking')}>
            <select
              className="select w-full"
              {...form.register('ranking_id', { valueAsNumber: true })}
            >
              {rankings.map((ranking) => (
                <option key={ranking.id} value={ranking.id}>
                  {t('stages.rankingOption', {
                    draw: formatPoints(ranking.draw_points),
                    loss: formatPoints(ranking.loss_points),
                    position: ranking.position + 1,
                    win: formatPoints(ranking.win_points),
                  })}
                </option>
              ))}
            </select>
          </Field>
        ) : null}
        <div className="md:col-span-4">
          <button className="btn btn-primary mt-3" type="submit">
            {t('stages.createItem')}
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
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  // A stage item named after its format, as those created without a name are, is shown with
  // the format's name in the page's language. It keeps its stored name unless another is typed.
  const shownName = stageItemName(stageItem, shared);
  const form = useSavedForm({
    resolver: zodResolver(zStageItemUpdateBody),
    values: { name: shownName },
  });
  const update = useMutation({
    ...form.saveCallbacks,
    ...updateStageItemApiTournamentsTournamentIdStageItemsStageItemIdPutMutation(),
    meta: { successMessage: t('stages.nameSaved') },
  });
  const remove = useMutation({
    ...deleteStageItemApiTournamentsTournamentIdStageItemsStageItemIdDeleteMutation(),
    meta: { successMessage: t('stages.itemDeleted') },
  });
  const path = { stage_item_id: stageItem.id, tournament_id: tournamentId };

  return (
    <form
      className="flex flex-col gap-2 md:flex-row"
      onSubmit={form.handleSubmit((body) =>
        update.mutate({
          body: { name: body.name === shownName ? stageItem.name : body.name },
          path,
        }),
      )}
    >
      <input
        aria-label={t('stages.itemName')}
        className="input w-full"
        placeholder={t('stages.itemName')}
        {...form.register('name')}
      />
      <SaveButton dirty={form.formState.isDirty} disabled={update.isPending}>
        {t('stages.saveName')}
      </SaveButton>
      <button
        className="btn btn-error btn-soft"
        disabled={remove.isPending}
        onClick={async () => {
          const fed = fedStageItems.map((item) => stageItemName(item, shared)).join(', ');
          const question = t('stages.deleteItemQuestion', {
            name: shownName,
          });
          if (
            await confirm({
              confirmLabel: t('stages.deleteItemConfirm'),
              destructive: true,
              message: fed
                ? `${question} ${t('stages.deleteItemFeeds', { items: fed })}`
                : question,
            })
          ) {
            remove.mutate({ path });
          }
        }}
        type="button"
      >
        {t('stages.deleteItem')}
      </button>
    </form>
  );
}

/** What a stage item has come to so far, as the Details pages show it: its table or its bracket. */
function StageItemOutcome({
  stageItem,
  stageItemsById,
  standings,
  teamMap,
  tournamentId,
}: {
  stageItem: OpenApi.StageItemWithRounds;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  standings: TournamentBundle['standings'];
  teamMap: Map<number, OpenApi.TournamentTeamWithPlayers>;
  tournamentId: number;
}) {
  const { t } = useTranslation();

  if (isBracket(stageItem)) {
    const bracketData = toBracketViewerData(stageItem, stageItemsById, tournamentId, t);
    return (
      <section className="space-y-4 rounded-box border border-base-300 bg-base-200/60 p-4">
        <h5 className="font-semibold">{t('tournament.bracket')}</h5>
        {bracketData ? (
          <BracketViewer data={bracketData} />
        ) : (
          <p className="text-sm text-base-content/70">{t('overview.bracketPending')}</p>
        )}
      </section>
    );
  }

  const entries = stageItemStandings(stageItem, standings);
  return (
    <section className="space-y-4 rounded-box border border-base-300 bg-base-200/60 p-4">
      <h5 className="font-semibold">{t('overview.table')}</h5>
      {entries.length === 0 ? (
        <p className="text-sm text-base-content/70">{t('overview.noTeams')}</p>
      ) : (
        <ol className="space-y-2">
          {entries.map(({ input, standing }, index) => (
            <li
              className="flex items-center justify-between gap-3 rounded-field border border-base-300 bg-base-100/60 px-3 py-2 text-sm"
              key={input.id}
            >
              <span className="flex items-center gap-3">
                <span className="w-5 text-base-content/70">{index + 1}</span>
                <TeamLink className="font-medium" teamId={input.team_id}>
                  {teamMap.get(input.team_id)?.name ?? inputLabel(input, stageItemsById, t)}
                </TeamLink>
              </span>
              <span className="text-base-content/70">
                {t('common.record', {
                  draws: standing.draws,
                  losses: standing.losses,
                  wins: standing.wins,
                })}{' '}
                · {pointsPhrase(stageItem, standing.points, t)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function StagesSection({ bundle }: { bundle: TournamentBundle }) {
  const { t } = useOrganizerTranslation();
  const { t: shared } = useTranslation();
  // A link to a stage item, such as a card of the overview, opens the stage it is in.
  const { hash } = useLocation();
  const focusId = Number(/^#stage-item-(\d+)$/.exec(hash)?.[1]);
  const teamLookup = new Map(bundle.teams.map((team) => [team.id, team] as const));
  const rankings = bundle.rankings.toSorted((left, right) => left.position - right.position);
  const stageItemsById = new Map(
    bundle.stages.flatMap((stage) => stage.stage_items.map((item) => [item.id, item] as const)),
  );
  const path = { tournament_id: bundle.tournament.id };
  const createStage = useMutation({
    ...createStageApiTournamentsTournamentIdStagesPostMutation(),
    meta: { successMessage: t('stages.created') },
  });
  const activateNext = useMutation({
    ...activateNextStageApiTournamentsTournamentIdStagesActivatePostMutation(),
    meta: { successMessage: t('stages.movedForward') },
  });
  const activatePrevious = useMutation({
    ...activateNextStageApiTournamentsTournamentIdStagesActivatePostMutation(),
    meta: { successMessage: t('stages.movedBack') },
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
        ? [t('stages.unplayed', { count: withoutResult, stage: stageName(activeStage, shared) })]
        : []),
      ...seedingDecides.map(({ team, tiedTeam }) =>
        t('stages.seedingDecides', { team: team.name, tied: tiedTeam.name }),
      ),
    ];
    if (
      reasons.length > 0 &&
      !(await confirm({
        confirmLabel: t('stages.activateNext'),
        message: (
          <>
            {reasons.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
            <p>{t('stages.activateNextAnyway')}</p>
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
        confirmLabel: t('stages.goBack'),
        destructive: true,
        message: t('stages.goBackQuestion', {
          count: results,
          stage: stageName(activeStage, shared),
        }),
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
                {t('stages.add')}
              </button>
              <button
                className="btn btn-soft btn-sm"
                disabled={!hasNextStage || activateNext.isPending}
                onClick={() => void goForward()}
                type="button"
              >
                {t('stages.activateNext')}
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={!hasPreviousStage || activatePrevious.isPending}
                onClick={() => void goBack()}
                type="button"
              >
                {t('stages.activatePrevious')}
              </button>
            </div>
          }
          title={shared('workspace.stages')}
        />
        <p className="text-sm text-base-content/70">{t('stages.editorHelp')}</p>
      </Surface>
      {bundle.stages.map((stage) => (
        <Disclosure
          className="collapse collapse-arrow border border-base-300 bg-base-200/60"
          key={stage.id}
          open={stage.is_active || stage.stage_items.some((item) => item.id === focusId)}
          summary={
            <>
              <span className="flex flex-wrap items-center gap-2">
                <span
                  className={cx(
                    'badge badge-soft badge-sm',
                    stage.is_active ? 'badge-accent' : null,
                  )}
                >
                  {stage.is_active ? t('stages.active') : t('stages.inactive')}
                </span>
                <span className="text-sm text-base-content/70">
                  {t('stages.itemCount', { count: stage.stage_items.length })}
                </span>
              </span>
              <span className="mt-2 block font-display text-2xl font-semibold">
                {stageName(stage, shared)}
              </span>
            </>
          }
        >
          <div className="collapse-content space-y-5">
            <StageForm stage={stage} tournament={bundle.tournament} />
            {stage.stage_items.map((stageItem) => (
              <details
                className="collapse collapse-arrow scroll-mt-6 border border-base-300 bg-base-100/50"
                id={`stage-item-${stageItem.id}`}
                key={stageItem.id}
                open
              >
                <summary className="collapse-title">
                  <span className="badge badge-soft badge-sm">
                    {stageTypeName(stageItem, shared)}
                  </span>
                  <span className="mt-2 block text-xl font-semibold">
                    {stageItemName(stageItem, shared)}
                  </span>
                  <span className="mt-1 block text-sm text-base-content/70">
                    {stageItemStatus(stageItem, t, shared)}
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
                    <h5 className="font-semibold">{t('stages.rounds')}</h5>
                    <StageItemRounds
                      stageItem={stageItem}
                      stageItemsById={stageItemsById}
                      tournamentId={bundle.tournament.id}
                    />
                  </section>
                  <StageItemOutcome
                    stageItem={stageItem}
                    stageItemsById={stageItemsById}
                    standings={bundle.standings}
                    teamMap={teamLookup}
                    tournamentId={bundle.tournament.id}
                  />
                </div>
              </details>
            ))}
            {/* Open while the stage has nothing else: adding a stage item is the next step. */}
            <Disclosure
              className="collapse collapse-arrow border border-base-300 bg-base-100/40"
              open={stage.stage_items.length === 0}
              summary={<span className="font-semibold">{t('stages.newItem')}</span>}
            >
              <NewStageItemForm
                rankings={rankings}
                stageId={stage.id}
                tournamentId={bundle.tournament.id}
              />
            </Disclosure>
          </div>
        </Disclosure>
      ))}
    </div>
  );
}
