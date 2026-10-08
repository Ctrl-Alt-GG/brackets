import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router';

import * as OpenApi from '../../openapi';
import {
  activateNextStageApiTournamentsTournamentIdStagesActivatePostMutation,
  changeStatusApiTournamentsTournamentIdChangeStatusPostMutation,
  createRankingApiTournamentsTournamentIdRankingsPostMutation,
  createStageApiTournamentsTournamentIdStagesPostMutation,
  createStageItemApiTournamentsTournamentIdStageItemsPostMutation,
  deleteRankingApiTournamentsTournamentIdRankingsRankingIdDeleteMutation,
  deleteStageApiTournamentsTournamentIdStagesStageIdDeleteMutation,
  deleteStageItemApiTournamentsTournamentIdStageItemsStageItemIdDeleteMutation,
  deleteTournamentApiTournamentsTournamentIdDeleteMutation,
  getTournamentsApiTournamentsGetQueryKey,
  updateRankingByIdApiTournamentsTournamentIdRankingsRankingIdPutMutation,
  updateStageApiTournamentsTournamentIdStagesStageIdPutMutation,
  updateStageItemApiTournamentsTournamentIdStageItemsStageItemIdPutMutation,
  updateTournamentByIdApiTournamentsTournamentIdPutMutation,
  uploadLogoApiTournamentsTournamentIdLogoPostMutation,
} from '../../openapi/@tanstack/react-query.gen';
import {
  zRankingBody,
  zRankingCreateBody,
  zStageItemCreateBody,
  zStageItemUpdateBody,
  zStageUpdateBody,
  zTournamentUpdateBody,
} from '../../openapi/zod.gen';
import { TournamentStatusBadge } from '../components/tournament-status-badge';
import { StageItemRounds, stageItemStatus } from './stage-item-rounds';
import { StageItemSlots } from './stage-item-slots';
import { StageItemVisualization } from './tournament-overview';
import { StandingsSection } from './tournament-standings';
import type { TournamentBundle } from '../types';
import {
  cx,
  DETAILS_PAGE_DESCRIPTION,
  formatPoints,
  normalizeDashboardEndpoint,
  publicTournamentPath,
  toDateTimeLocal,
} from '../utils';
import { zLocalDateTime } from '../forms';
import { CheckboxField, Field, Surface, SurfaceHeading } from '../ui';

const ADD_SCORE_POINTS_DESCRIPTION =
  'Teams also get their score in each match added to their points.';

const POINT_FIELDS = [
  ['win_points', 'Win points'],
  ['draw_points', 'Draw points'],
  ['loss_points', 'Loss points'],
] as const;

function NewRankingForm({ tournamentId }: { tournamentId: number }) {
  const form = useForm({
    defaultValues: { add_score_points: false, draw_points: 1, loss_points: 0, win_points: 3 },
    resolver: zodResolver(zRankingCreateBody),
  });
  const create = useMutation({
    ...createRankingApiTournamentsTournamentIdRankingsPostMutation(),
    meta: { successMessage: 'Ranking created.' },
  });

  return (
    <form
      onSubmit={form.handleSubmit((body) =>
        create.mutate(
          { body, path: { tournament_id: tournamentId } },
          { onSuccess: () => form.reset() },
        ),
      )}
    >
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
      <button className="btn btn-primary mt-4" disabled={create.isPending} type="submit">
        Create ranking
      </button>
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
  const form = useForm({
    resetOptions: { keepDirtyValues: true },
    resolver: zodResolver(zRankingBody),
    // Follows the saved ranking, without throwing away what the organizer is typing.
    values: {
      add_score_points: ranking.add_score_points,
      draw_points: ranking.draw_points,
      loss_points: ranking.loss_points,
      position: ranking.position,
      win_points: ranking.win_points,
    },
  });
  const update = useMutation({
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
    <details className="collapse collapse-arrow border border-base-300 bg-base-100/50">
      <summary className="collapse-title">
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
      </summary>
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
            onClick={() => {
              if (window.confirm(`Delete ranking #${ranking.position}?`)) remove.mutate({ path });
            }}
            type="button"
          >
            Delete ranking
          </button>
        </div>
      </form>
    </details>
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

const tournamentSettingsSchema = zTournamentUpdateBody.extend({ start_time: zLocalDateTime });

function TournamentSettingsForm({ tournament }: { tournament: OpenApi.Tournament }) {
  const form = useForm({
    resetOptions: { keepDirtyValues: true },
    resolver: zodResolver(tournamentSettingsSchema),
    values: {
      dashboard_endpoint: normalizeDashboardEndpoint(tournament.dashboard_endpoint) ?? '',
      dashboard_public: tournament.dashboard_public,
      duration_minutes: tournament.duration_minutes,
      margin_minutes: tournament.margin_minutes,
      name: tournament.name,
      players_can_be_in_multiple_teams: tournament.players_can_be_in_multiple_teams,
      start_time: toDateTimeLocal(tournament.start_time),
    },
  });
  const update = useMutation({
    ...updateTournamentByIdApiTournamentsTournamentIdPutMutation(),
    meta: { successMessage: 'Tournament saved.' },
  });
  const uploadLogo = useMutation({
    ...uploadLogoApiTournamentsTournamentIdLogoPostMutation(),
    meta: { successMessage: 'Logo uploaded.' },
  });
  const path = { tournament_id: tournament.id };
  const { errors } = form.formState;

  return (
    <form onSubmit={form.handleSubmit((body) => update.mutate({ body, path }))}>
      <div className="grid gap-x-4 md:grid-cols-2">
        <Field error={errors.name?.message} label="Tournament name">
          <input className="input w-full" required {...form.register('name')} />
        </Field>
        <Field label="Details link">
          <input
            className="input w-full"
            placeholder="summer-cup-2026"
            {...form.register('dashboard_endpoint')}
          />
        </Field>
        <Field error={errors.start_time?.message} label="Start time">
          <input
            className="input w-full"
            required
            type="datetime-local"
            {...form.register('start_time')}
          />
        </Field>
        <Field label="Tournament logo">
          <input
            accept="image/*"
            className="file-input w-full"
            disabled={uploadLogo.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) uploadLogo.mutate({ body: { file }, path });
            }}
            type="file"
          />
        </Field>
        <Field error={errors.duration_minutes?.message} label="Match duration (minutes)">
          <input
            className="input w-full"
            min={1}
            required
            type="number"
            {...form.register('duration_minutes', { valueAsNumber: true })}
          />
        </Field>
        <Field error={errors.margin_minutes?.message} label="Break between rounds (minutes)">
          <input
            className="input w-full"
            min={0}
            required
            type="number"
            {...form.register('margin_minutes', { valueAsNumber: true })}
          />
        </Field>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <CheckboxField
          description={DETAILS_PAGE_DESCRIPTION}
          label="Details page enabled"
          {...form.register('dashboard_public')}
        />
        <CheckboxField
          label="Players can join multiple teams"
          {...form.register('players_can_be_in_multiple_teams')}
        />
      </div>
      <button className="btn btn-primary mt-4" disabled={update.isPending} type="submit">
        {update.isPending ? 'Saving…' : 'Save tournament'}
      </button>
    </form>
  );
}

export function SettingsSection({ bundle }: { bundle: TournamentBundle }) {
  const navigate = useNavigate();
  const tournament = bundle.tournament;
  const isOpen = tournament.status === 'OPEN';
  const detailsPath = publicTournamentPath(tournament);
  const path = { tournament_id: tournament.id };
  const changeStatus = useMutation({
    ...changeStatusApiTournamentsTournamentIdChangeStatusPostMutation(),
    meta: { successMessage: isOpen ? 'Tournament archived.' : 'Tournament reopened.' },
  });
  const remove = useMutation({
    ...deleteTournamentApiTournamentsTournamentIdDeleteMutation(),
    // Reloading the deleted tournament would fail as unauthorized, which logs the organizer out.
    meta: {
      invalidates: [getTournamentsApiTournamentsGetQueryKey()],
      successMessage: 'Tournament deleted.',
    },
    onSuccess: () => navigate('/'),
  });

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[1fr_0.8fr]">
      <Surface>
        <SurfaceHeading title="Tournament settings" />
        <TournamentSettingsForm tournament={tournament} />
      </Surface>

      <Surface>
        <SurfaceHeading title="Status and sharing" />
        <section className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            Status: <TournamentStatusBadge tournament={tournament} />
          </div>
          <p className="text-sm text-base-content/70">
            {isOpen
              ? 'Archive the tournament once it is over. Archived tournaments can no longer be changed.'
              : 'This tournament is archived. Reopen it to make changes again.'}
          </p>
          <button
            className="btn btn-soft"
            disabled={changeStatus.isPending}
            onClick={() =>
              changeStatus.mutate({ body: { status: isOpen ? 'ARCHIVED' : 'OPEN' }, path })
            }
            type="button"
          >
            {isOpen ? 'Archive tournament' : 'Reopen tournament'}
          </button>
        </section>

        <section className="space-y-2 border-t border-base-300 pt-5">
          <h3 className="text-sm font-medium">Details page</h3>
          {tournament.dashboard_public ? (
            <p className="text-sm text-base-content/80">
              Share this link with players:{' '}
              <Link className="link break-all" to={detailsPath}>
                {detailsPath}
              </Link>
            </p>
          ) : (
            <p className="text-sm text-base-content/70">
              Turn on “Details page enabled” to share a link to it, and to keep it visible after the
              tournament is archived.
            </p>
          )}
        </section>

        <section className="space-y-3 border-t border-base-300 pt-5">
          <h3 className="text-sm font-medium">Delete tournament</h3>
          <p className="text-sm text-base-content/70">
            Deletes the tournament with its teams, players and results. This cannot be undone.
          </p>
          <button
            className="btn btn-error"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete ${tournament.name}? This cannot be undone.`)) {
                remove.mutate({ path });
              }
            }}
            type="button"
          >
            Delete tournament
          </button>
        </section>
      </Surface>
    </div>
  );
}

function StageForm({
  stage,
  tournament,
}: {
  stage: OpenApi.StageWithStageItems;
  tournament: OpenApi.Tournament;
}) {
  const form = useForm({
    resetOptions: { keepDirtyValues: true },
    resolver: zodResolver(zStageUpdateBody),
    values: { custom_duration_minutes: stage.custom_duration_minutes, name: stage.name },
  });
  const update = useMutation({
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
        onClick={() => {
          if (window.confirm(`Delete stage ${stage.name}?`)) remove.mutate({ path });
        }}
        type="button"
      >
        Delete stage
      </button>
    </form>
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
  const form = useForm({
    defaultValues: {
      name: '',
      ranking_id: rankings[0]?.id ?? null,
      stage_id: stageId,
      team_count: 8,
      type: 'ROUND_ROBIN' as const,
    },
    resolver: zodResolver(zStageItemCreateBody),
  });
  const create = useMutation({
    ...createStageItemApiTournamentsTournamentIdStageItemsPostMutation(),
    meta: { successMessage: 'Stage item created.' },
  });

  return (
    <form
      className="grid items-end gap-x-4 rounded-box border border-base-300 bg-base-100/40 p-4 md:grid-cols-4"
      onSubmit={form.handleSubmit((body) =>
        create.mutate(
          {
            body: { ...body, name: body.name?.trim() || null },
            path: { tournament_id: tournamentId },
          },
          { onSuccess: () => form.reset() },
        ),
      )}
    >
      <Field label="Name">
        <input className="input w-full" placeholder="Upper bracket" {...form.register('name')} />
      </Field>
      <Field label="Type">
        <select className="select w-full" {...form.register('type')}>
          <option value="ROUND_ROBIN">Round robin</option>
          <option value="SINGLE_ELIMINATION">Single elimination</option>
          <option value="SWISS">Swiss</option>
        </select>
      </Field>
      <Field error={form.formState.errors.team_count?.message} label="Team count">
        <input
          className="input w-full"
          max={64}
          min={2}
          required
          type="number"
          {...form.register('team_count', { valueAsNumber: true })}
        />
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
        <button className="btn btn-primary mt-3" disabled={create.isPending} type="submit">
          Create stage item
        </button>
      </div>
    </form>
  );
}

function StageItemNameForm({
  stageItem,
  tournamentId,
}: {
  stageItem: OpenApi.StageItemWithRounds;
  tournamentId: number;
}) {
  const form = useForm({
    resetOptions: { keepDirtyValues: true },
    resolver: zodResolver(zStageItemUpdateBody),
    values: { name: stageItem.name, ranking_id: stageItem.ranking_id ?? 0 },
  });
  const update = useMutation({
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
        onClick={() => {
          if (window.confirm(`Delete stage item ${stageItem.name || stageItem.type_name}?`)) {
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
                disabled={activateNext.isPending}
                onClick={() => activateNext.mutate({ body: { direction: 'next' }, path })}
                type="button"
              >
                Activate next stage
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={activatePrevious.isPending}
                onClick={() => activatePrevious.mutate({ body: { direction: 'previous' }, path })}
                type="button"
              >
                Activate previous stage
              </button>
            </div>
          }
          title="Bracket editor"
        />
        {focusStageItem ? (
          <div className="alert alert-soft alert-warning text-sm">
            Focusing stage item <strong>{focusStageItem.name || focusStageItem.type_name}</strong>{' '}
            via the swiss route.
          </div>
        ) : null}
      </Surface>
      {bundle.stages.map((stage) => (
        <details
          className="collapse collapse-arrow border border-base-300 bg-base-200/60"
          key={stage.id}
          open={stage.is_active || stage.stage_items.some((item) => item.id === focusStageItem?.id)}
        >
          <summary className="collapse-title">
            <span className="flex flex-wrap items-center gap-2">
              <span
                className={cx('badge badge-soft badge-sm', stage.is_active ? 'badge-accent' : null)}
              >
                {stage.is_active ? 'Active' : 'Inactive'}
              </span>
              <span className="text-sm text-base-content/70">
                {stage.stage_items.length} stage items
              </span>
            </span>
            <span className="mt-2 block font-display text-2xl font-semibold">{stage.name}</span>
          </summary>
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
                  <StageItemNameForm stageItem={stageItem} tournamentId={bundle.tournament.id} />
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
        </details>
      ))}
    </div>
  );
}
