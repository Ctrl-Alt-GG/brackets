import type { FormEvent } from 'react';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import { runAction } from '../hooks';
import { DateTimeField } from '../components/date-time-field';
import { MatchCard } from '../components/match-card';
import { StageItemRounds, stageItemStatus } from './stage-item-rounds';
import { StageItemSlots } from './stage-item-slots';
import { StageItemVisualization } from './tournament-overview';
import type { FlashMessage, FlattenedMatch, TournamentBundle } from '../types';
import {
  cx,
  formatDateTime,
  formatPoints,
  formatScoreDifference,
  inputLabel,
  isScored,
  matchStatus,
  normalizeDashboardEndpoint,
  pointsLabel,
  pointsPhrase,
  stageItemStandings,
  toCheckbox,
  toNumber,
  toOptionalNumber,
  toOptionalString,
} from '../utils';
import { Button, FormField, Input, Pill, Select, Surface, SurfaceHeading, Textarea } from '../ui';

export function ScheduleSection({
  compact,
  isAuthenticated,
  matches,
  onRefresh,
  setFlash,
  stageItemsById,
  tournamentId,
}: {
  compact?: boolean;
  isAuthenticated: boolean;
  matches: FlattenedMatch[];
  onRefresh: () => void;
  setFlash: (message: FlashMessage) => void;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  tournamentId: number;
}) {
  // Matches arrive sorted by start time, so the slots keep that order.
  const slots = new Map<string, FlattenedMatch[]>();
  matches
    .filter(({ match }) => !compact || matchStatus(match) !== 'finished')
    .forEach((entry) => {
      const startTime = entry.match.start_time ?? '';
      slots.set(startTime, [...(slots.get(startTime) ?? []), entry]);
    });
  const shownSlots = [...slots.entries()].slice(0, compact ? 2 : undefined);

  return (
    <Surface className="space-y-6">
      <SurfaceHeading
        actions={
          isAuthenticated && !compact ? (
            <Button
              onClick={async () => {
                await runAction(
                  setFlash,
                  async () => {
                    await OpenApi.scheduleMatchesApiTournamentsTournamentIdScheduleMatchesPost({
                      path: { tournament_id: tournamentId },
                      throwOnError: true,
                    });
                  },
                  'Match times recalculated.',
                  onRefresh,
                );
              }}
              tone="secondary"
              type="button"
            >
              Recalculate times
            </Button>
          ) : null
        }
        title={compact ? 'Now and next' : 'Schedule'}
      />
      {isAuthenticated && !compact ? (
        <p className="text-sm text-zinc-400">
          Match times are planned automatically: all matches of a round start together, and a round
          starts when the previous one has finished. To move the schedule, change the start time,
          match duration or break in Settings, or the match duration of a stage in Stages.
        </p>
      ) : null}
      {shownSlots.length === 0 ? (
        <p className="text-sm text-zinc-400">
          {compact ? 'All matches are finished.' : 'No matches have been scheduled yet.'}
        </p>
      ) : null}
      {shownSlots.map(([startTime, entries]) => (
        <section className="space-y-3" key={startTime || 'unscheduled'}>
          <h3
            className={cx(
              'font-display font-semibold text-white',
              compact ? 'text-3xl' : 'text-xl',
            )}
          >
            {startTime ? formatDateTime(startTime) : 'Not scheduled yet'}
          </h3>
          <div
            className={cx(
              'grid gap-3',
              compact ? 'xl:grid-cols-2' : 'md:grid-cols-2 xl:grid-cols-3',
            )}
          >
            {entries.map((entry) => (
              <MatchCard
                entry={entry}
                key={entry.match.id}
                size={compact ? 'lg' : 'md'}
                stageItemsById={stageItemsById}
              />
            ))}
          </div>
        </section>
      ))}
    </Surface>
  );
}

export function StandingsSection({
  compact,
  rankings,
  stages,
  standings,
  teamMap,
}: {
  compact?: boolean;
  rankings: OpenApi.Ranking[];
  stages: OpenApi.StageWithStageItems[];
  standings: TournamentBundle['standings'];
  teamMap: Map<number, OpenApi.FullTeamWithPlayers>;
}) {
  // Results are kept per stage item, and teams only compete for a place within their own group.
  const tables = stages.flatMap((stage) =>
    stage.stage_items
      .map((stageItem) => ({ entries: stageItemStandings(stageItem, standings), stage, stageItem }))
      .filter(({ entries }) => entries.length > 0),
  );
  const hasSwiss = tables.some(({ stageItem }) => stageItem.type === 'SWISS');

  return (
    <div className="space-y-6">
      <Surface className="space-y-6">
        <SurfaceHeading actions={<Pill>{`${teamMap.size} teams`}</Pill>} title="Standings" />
        {tables.length === 0 ? (
          <p className="text-sm text-zinc-400">No standings yet: no team has joined a group.</p>
        ) : null}
        {tables.map(({ entries, stage, stageItem }) => (
          <section className="space-y-3" key={stageItem.id}>
            <div>
              <h3 className="text-lg font-semibold text-white">
                {stageItem.name || stageItem.type_name}
              </h3>
              <p className="text-sm text-zinc-400">
                {stage.name} · {stageItem.type_name}
              </p>
            </div>
            {compact ? (
              <div className="grid gap-3">
                {entries.map(({ input, standing }, index) => (
                  <div
                    className="grid grid-cols-[auto_1fr_auto] items-center gap-4 rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-4"
                    key={input.id}
                  >
                    <div className="min-w-12 text-center">
                      <p className="font-display text-3xl font-semibold text-white">{index + 1}</p>
                    </div>
                    <p className="font-display text-2xl font-semibold text-white">
                      {input.team.name}
                    </p>
                    <p className="text-right text-lg text-zinc-300">
                      <span className="font-semibold text-emerald-300">{standing.wins}</span> won ·{' '}
                      {standing.draws} drawn · {standing.losses} lost ·{' '}
                      <span className="font-semibold text-white">
                        {pointsPhrase(stageItem, standing.points)}
                      </span>
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm text-zinc-200">
                  <thead>
                    <tr className="border-b border-white/10 text-xs uppercase tracking-[0.3em] text-zinc-400">
                      <th className="px-3 py-3">#</th>
                      <th className="px-3 py-3">Team</th>
                      <th className="px-3 py-3">Players</th>
                      <th className="px-3 py-3">Played</th>
                      <th className="px-3 py-3">Won</th>
                      <th className="px-3 py-3">Drawn</th>
                      <th className="px-3 py-3">Lost</th>
                      <th className="px-3 py-3" title="Score difference">
                        +/−
                      </th>
                      <th className="px-3 py-3">{pointsLabel(stageItem)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map(({ input, standing }, index) => (
                      <tr className="border-b border-white/5" key={input.id}>
                        <td className="px-3 py-4 text-zinc-500">{index + 1}</td>
                        <td className="px-3 py-4 font-semibold text-white">{input.team.name}</td>
                        <td className="px-3 py-4 text-zinc-400">
                          {teamMap
                            .get(input.team_id)
                            ?.players.map((player) => player.name)
                            .join(', ') || '—'}
                        </td>
                        <td className="px-3 py-4">
                          {standing.wins + standing.draws + standing.losses}
                        </td>
                        <td className="px-3 py-4">{standing.wins}</td>
                        <td className="px-3 py-4">{standing.draws}</td>
                        <td className="px-3 py-4">{standing.losses}</td>
                        <td
                          className="px-3 py-4"
                          title={`${standing.score_for} scored, ${standing.score_against} conceded`}
                        >
                          {formatScoreDifference(standing)}
                        </td>
                        <td className="px-3 py-4 font-semibold text-white">
                          {formatPoints(standing.points)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ))}
      </Surface>
      {!compact ? (
        <Surface className="space-y-4">
          <SurfaceHeading title="How points are awarded" />
          <div className="grid gap-4 lg:grid-cols-2">
            {rankings.map((ranking) => (
              <div
                className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4"
                key={ranking.id}
              >
                <p className="text-sm text-zinc-300">
                  A win is worth {ranking.win_points} points, a draw {ranking.draw_points} and a
                  loss {ranking.loss_points}.
                </p>
              </div>
            ))}
          </div>
          <p className="text-sm text-zinc-400">
            Teams with the same points are ranked by score difference, then by their total score,
            then by the number of wins, and after that by their seeding. Teams go through to the
            next stage in this order.
            {hasSwiss
              ? ' In Swiss groups, teams are ranked by a rating that starts at 1200 and changes with every result.'
              : null}
          </p>
        </Surface>
      ) : null}
    </div>
  );
}

export function RankingsSection({
  bundle,
  onRefresh,
  setFlash,
  teamMap,
}: {
  bundle: TournamentBundle;
  onRefresh: () => void;
  setFlash: (message: FlashMessage) => void;
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
      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <Surface className="space-y-4">
          <SurfaceHeading title="Ranking rule" />
          <form
            className="space-y-4"
            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              const form = event.currentTarget;
              const formData = new FormData(form);
              await runAction(
                setFlash,
                async () => {
                  await OpenApi.createRankingApiTournamentsTournamentIdRankingsPost({
                    body: {
                      add_score_points: toCheckbox(formData.get('add_score_points')),
                      draw_points: toNumber(formData.get('draw_points')),
                      loss_points: toNumber(formData.get('loss_points')),
                      win_points: toNumber(formData.get('win_points')),
                    },
                    path: { tournament_id: bundle.tournament.id },
                    throwOnError: true,
                  });
                },
                'Ranking created successfully.',
                () => {
                  form.reset();
                  onRefresh();
                },
              );
            }}
          >
            <div className="grid gap-4 md:grid-cols-2">
              <FormField label="Win points">
                <Input defaultValue={3} name="win_points" type="number" />
              </FormField>
              <FormField label="Draw points">
                <Input defaultValue={1} name="draw_points" type="number" />
              </FormField>
              <FormField label="Loss points">
                <Input defaultValue={0} name="loss_points" type="number" />
              </FormField>
              <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
                <input
                  className="h-4 w-4 accent-brand-500"
                  name="add_score_points"
                  type="checkbox"
                />
                <span>Add raw score points</span>
              </label>
            </div>
            <Button type="submit">Create ranking</Button>
          </form>
        </Surface>

        <Surface className="space-y-4">
          <SurfaceHeading
            actions={<Pill>{`${bundle.rankings.length} rankings`}</Pill>}
            title="Ranking definitions"
          />
          <div className="space-y-4">
            {bundle.rankings.map((ranking) => (
              <details
                className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4"
                key={ranking.id}
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-white">Ranking #{ranking.position}</h3>
                    <p className="text-sm text-zinc-400">
                      Win {ranking.win_points} · Draw {ranking.draw_points} · Loss{' '}
                      {ranking.loss_points}
                    </p>
                  </div>
                  {ranking.add_score_points ? (
                    <Pill tone="accent">score-aware</Pill>
                  ) : (
                    <Pill>flat</Pill>
                  )}
                </summary>
                <form
                  className="mt-4 grid gap-4 md:grid-cols-2"
                  onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                    event.preventDefault();
                    const formData = new FormData(event.currentTarget);
                    await runAction(
                      setFlash,
                      async () => {
                        await OpenApi.updateRankingByIdApiTournamentsTournamentIdRankingsRankingIdPut(
                          {
                            body: {
                              add_score_points: toCheckbox(formData.get('add_score_points')),
                              draw_points: toNumber(formData.get('draw_points')),
                              loss_points: toNumber(formData.get('loss_points')),
                              position: toNumber(formData.get('position')),
                              win_points: toNumber(formData.get('win_points')),
                            },
                            path: { ranking_id: ranking.id, tournament_id: bundle.tournament.id },
                            throwOnError: true,
                          },
                        );
                      },
                      'Ranking updated successfully.',
                      onRefresh,
                    );
                  }}
                >
                  <FormField label="Position">
                    <Input defaultValue={ranking.position} name="position" type="number" />
                  </FormField>
                  <FormField label="Win points">
                    <Input defaultValue={ranking.win_points} name="win_points" type="number" />
                  </FormField>
                  <FormField label="Draw points">
                    <Input defaultValue={ranking.draw_points} name="draw_points" type="number" />
                  </FormField>
                  <FormField label="Loss points">
                    <Input defaultValue={ranking.loss_points} name="loss_points" type="number" />
                  </FormField>
                  <label className="md:col-span-2 flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
                    <input
                      className="h-4 w-4 accent-brand-500"
                      defaultChecked={ranking.add_score_points}
                      name="add_score_points"
                      type="checkbox"
                    />
                    <span>Add raw score points</span>
                  </label>
                  <div className="md:col-span-2 flex flex-wrap gap-3">
                    <Button type="submit">Save ranking</Button>
                    <Button
                      onClick={async () => {
                        if (!window.confirm(`Delete ranking #${ranking.position}?`)) return;
                        await runAction(
                          setFlash,
                          async () => {
                            await OpenApi.deleteRankingApiTournamentsTournamentIdRankingsRankingIdDelete(
                              {
                                path: {
                                  ranking_id: ranking.id,
                                  tournament_id: bundle.tournament.id,
                                },
                                throwOnError: true,
                              },
                            );
                          },
                          'Ranking deleted successfully.',
                          onRefresh,
                        );
                      }}
                      tone="danger"
                      type="button"
                    >
                      Delete ranking
                    </Button>
                  </div>
                </form>
              </details>
            ))}
          </div>
        </Surface>
      </div>
    </div>
  );
}

export function ResultsSection({
  matches,
  stageItemsById,
}: {
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
}) {
  const scoredMatches = matches.filter(({ match }) => isScored(match)).reverse();

  return (
    <Surface className="space-y-4">
      <SurfaceHeading
        actions={<Pill>{`${scoredMatches.length} scored matches`}</Pill>}
        title="Latest results"
      />
      <div className="grid gap-3">
        {scoredMatches.map(({ match, round, stage, stageItem }) => (
          <div className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4" key={match.id}>
            <p className="text-xs text-zinc-400">
              {stage.name} / {stageItem.name || stageItem.type_name} / {round.name}
            </p>
            <h3 className="mt-2 text-xl font-semibold text-white">
              {inputLabel(match.stage_item_input1, stageItemsById)}{' '}
              <span className="text-brand-300">{match.stage_item_input1_score}</span> -{' '}
              <span className="text-brand-300">{match.stage_item_input2_score}</span>{' '}
              {inputLabel(match.stage_item_input2, stageItemsById)}
            </h3>
            <p className="mt-2 text-sm text-zinc-400">{formatDateTime(match.start_time)}</p>
          </div>
        ))}
      </div>
    </Surface>
  );
}

export function SettingsSection({
  bundle,
  onRefresh,
  setFlash,
  tournamentKey,
}: {
  bundle: TournamentBundle;
  onRefresh: () => void;
  setFlash: (message: FlashMessage) => void;
  tournamentKey: string;
}) {
  const tournament = bundle.tournament;

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_0.8fr]">
      <Surface className="space-y-4">
        <SurfaceHeading title="Metadata and policy" />
        <form
          className="grid gap-4 md:grid-cols-2"
          onSubmit={async (event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const formData = new FormData(event.currentTarget);
            await runAction(
              setFlash,
              async () => {
                await OpenApi.updateTournamentByIdApiTournamentsTournamentIdPut({
                  body: {
                    dashboard_endpoint: toOptionalString(formData.get('dashboard_endpoint')),
                    dashboard_public: toCheckbox(formData.get('dashboard_public')),
                    duration_minutes: toNumber(formData.get('duration_minutes')),
                    margin_minutes: toNumber(formData.get('margin_minutes')),
                    name: String(formData.get('name') ?? ''),
                    players_can_be_in_multiple_teams: toCheckbox(
                      formData.get('players_can_be_in_multiple_teams'),
                    ),
                    start_time: String(formData.get('start_time') ?? ''),
                  },
                  path: { tournament_id: tournament.id },
                  throwOnError: true,
                });

                const file = formData.get('logo');
                if (file instanceof File && file.size > 0) {
                  await OpenApi.uploadLogoApiTournamentsTournamentIdLogoPost({
                    body: { file },
                    path: { tournament_id: tournament.id },
                    throwOnError: true,
                  });
                }
              },
              'Tournament updated successfully.',
              onRefresh,
            );
          }}
        >
          <FormField label="Tournament name">
            <Input defaultValue={tournament.name} name="name" />
          </FormField>
          <FormField label="Dashboard endpoint">
            <Input
              defaultValue={normalizeDashboardEndpoint(tournament.dashboard_endpoint) ?? ''}
              name="dashboard_endpoint"
            />
          </FormField>
          <FormField label="Start time">
            <DateTimeField defaultValue={tournament.start_time} name="start_time" />
          </FormField>
          <FormField label="Tournament logo">
            <Input accept="image/*" name="logo" type="file" />
          </FormField>
          <FormField label="Match duration (minutes)">
            <Input
              defaultValue={tournament.duration_minutes}
              name="duration_minutes"
              type="number"
            />
          </FormField>
          <FormField label="Break between rounds (minutes)">
            <Input defaultValue={tournament.margin_minutes} name="margin_minutes" type="number" />
          </FormField>
          <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
            <input
              className="h-4 w-4 accent-brand-500"
              defaultChecked={tournament.dashboard_public}
              name="dashboard_public"
              type="checkbox"
            />
            <span>Public dashboard enabled</span>
          </label>
          <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
            <input
              className="h-4 w-4 accent-brand-500"
              defaultChecked={tournament.players_can_be_in_multiple_teams}
              name="players_can_be_in_multiple_teams"
              type="checkbox"
            />
            <span>Players can join multiple teams</span>
          </label>
          <div className="md:col-span-2">
            <Button type="submit">Save tournament</Button>
          </div>
        </form>
      </Surface>

      <Surface className="space-y-4">
        <SurfaceHeading title="Status and sharing" />
        <p className="text-sm text-zinc-300">
          Public dashboard link:{' '}
          <Link
            className="underline decoration-brand-400/50 underline-offset-4 hover:text-white"
            to={`/tournaments/${normalizeDashboardEndpoint(tournament.dashboard_endpoint) ?? tournamentKey}/dashboard`}
          >{`/tournaments/${normalizeDashboardEndpoint(tournament.dashboard_endpoint) ?? tournamentKey}/dashboard`}</Link>
        </p>
        <div className="grid gap-3">
          <Button
            onClick={async () => {
              await runAction(
                setFlash,
                async () => {
                  await OpenApi.changeStatusApiTournamentsTournamentIdChangeStatusPost({
                    body: { status: tournament.status === 'OPEN' ? 'ARCHIVED' : 'OPEN' },
                    path: { tournament_id: tournament.id },
                    throwOnError: true,
                  });
                },
                'Tournament status updated successfully.',
                onRefresh,
              );
            }}
            type="button"
          >
            Switch to {tournament.status === 'OPEN' ? 'ARCHIVED' : 'OPEN'}
          </Button>
          <Button
            onClick={async () => {
              if (!window.confirm(`Delete ${tournament.name}?`)) return;
              await runAction(
                setFlash,
                async () => {
                  await OpenApi.deleteTournamentApiTournamentsTournamentIdDelete({
                    path: { tournament_id: tournament.id },
                    throwOnError: true,
                  });
                },
                'Tournament deleted successfully. Return to the overview page.',
              );
            }}
            tone="danger"
            type="button"
          >
            Delete tournament
          </Button>
        </div>
      </Surface>
    </div>
  );
}

export function StagesSection({
  bundle,
  focusStageItem,
  onRefresh,
  setFlash,
}: {
  bundle: TournamentBundle;
  focusStageItem: OpenApi.StageItemWithRounds | null;
  onRefresh: () => void;
  setFlash: (message: FlashMessage) => void;
}) {
  const teamLookup = new Map(bundle.teams.map((team) => [team.id, team] as const));
  const rankings = [...bundle.rankings].sort((left, right) => left.position - right.position);
  const stageItemsById = new Map<number, OpenApi.StageItemWithRounds>();
  bundle.stages.forEach((stage) =>
    stage.stage_items.forEach((item) => stageItemsById.set(item.id, item)),
  );

  return (
    <div className="space-y-6">
      <Surface className="space-y-4">
        <SurfaceHeading
          actions={
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={async () => {
                  await runAction(
                    setFlash,
                    async () => {
                      await OpenApi.createStageApiTournamentsTournamentIdStagesPost({
                        path: { tournament_id: bundle.tournament.id },
                        throwOnError: true,
                      });
                    },
                    'Stage created successfully.',
                    onRefresh,
                  );
                }}
                type="button"
              >
                Add stage
              </Button>
              <Button
                onClick={async () => {
                  await runAction(
                    setFlash,
                    async () => {
                      await OpenApi.activateNextStageApiTournamentsTournamentIdStagesActivatePost({
                        body: { direction: 'next' },
                        path: { tournament_id: bundle.tournament.id },
                        throwOnError: true,
                      });
                    },
                    'Moved active stage forward.',
                    onRefresh,
                  );
                }}
                tone="secondary"
                type="button"
              >
                Activate next stage
              </Button>
              <Button
                onClick={async () => {
                  await runAction(
                    setFlash,
                    async () => {
                      await OpenApi.activateNextStageApiTournamentsTournamentIdStagesActivatePost({
                        body: { direction: 'previous' },
                        path: { tournament_id: bundle.tournament.id },
                        throwOnError: true,
                      });
                    },
                    'Moved active stage backward.',
                    onRefresh,
                  );
                }}
                tone="ghost"
                type="button"
              >
                Activate previous stage
              </Button>
            </div>
          }
          title="Bracket editor"
        />
        {focusStageItem ? (
          <div className="rounded-[1.25rem] border border-accent-400/30 bg-accent-500/10 p-4 text-sm text-accent-100">
            Focusing stage item <strong>{focusStageItem.name || focusStageItem.type_name}</strong>{' '}
            via the swiss route.
          </div>
        ) : null}
      </Surface>
      <div className="space-y-6">
        {bundle.stages.map((stage) => (
          <details
            className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5"
            key={stage.id}
            open={
              stage.is_active || stage.stage_items.some((item) => item.id === focusStageItem?.id)
            }
          >
            <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  {stage.is_active ? <Pill tone="accent">active</Pill> : <Pill>inactive</Pill>}
                  <Pill>{`${stage.stage_items.length} stage items`}</Pill>
                </div>
                <h3 className="mt-3 font-display text-2xl font-semibold text-white">
                  {stage.name}
                </h3>
              </div>
            </summary>
            <div className="mt-5 space-y-5">
              <form
                className="grid items-end gap-4 md:grid-cols-[1fr_1fr_auto_auto]"
                onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  await runAction(
                    setFlash,
                    async () => {
                      await OpenApi.updateStageApiTournamentsTournamentIdStagesStageIdPut({
                        body: {
                          custom_duration_minutes: toOptionalNumber(
                            formData.get('custom_duration_minutes'),
                          ),
                          name: String(formData.get('name') ?? ''),
                        },
                        path: { stage_id: stage.id, tournament_id: bundle.tournament.id },
                        throwOnError: true,
                      });
                    },
                    'Stage updated successfully.',
                    onRefresh,
                  );
                }}
              >
                <FormField label="Stage name">
                  <Input defaultValue={stage.name} name="name" />
                </FormField>
                <FormField label="Match duration (minutes)">
                  <Input
                    defaultValue={stage.custom_duration_minutes ?? ''}
                    min={1}
                    name="custom_duration_minutes"
                    placeholder={`Tournament default (${bundle.tournament.duration_minutes})`}
                    type="number"
                  />
                </FormField>
                <Button type="submit">Save stage</Button>
                <Button
                  onClick={async () => {
                    if (!window.confirm(`Delete stage ${stage.name}?`)) return;
                    await runAction(
                      setFlash,
                      async () => {
                        await OpenApi.deleteStageApiTournamentsTournamentIdStagesStageIdDelete({
                          path: { stage_id: stage.id, tournament_id: bundle.tournament.id },
                          throwOnError: true,
                        });
                      },
                      'Stage deleted successfully.',
                      onRefresh,
                    );
                  }}
                  tone="danger"
                  type="button"
                >
                  Delete stage
                </Button>
              </form>

              <form
                className="grid gap-4 rounded-[1.25rem] border border-white/10 bg-black/20 p-4 md:grid-cols-4"
                onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                  event.preventDefault();
                  const form = event.currentTarget;
                  const formData = new FormData(form);
                  await runAction(
                    setFlash,
                    async () => {
                      await OpenApi.createStageItemApiTournamentsTournamentIdStageItemsPost({
                        body: {
                          name: toOptionalString(formData.get('name')),
                          ranking_id: toOptionalNumber(formData.get('ranking_id')),
                          stage_id: stage.id,
                          team_count: toNumber(formData.get('team_count')),
                          type: String(formData.get('type') ?? 'ROUND_ROBIN') as OpenApi.StageType,
                        },
                        path: { tournament_id: bundle.tournament.id },
                        throwOnError: true,
                      });
                    },
                    'Stage item created successfully.',
                    () => {
                      form.reset();
                      onRefresh();
                    },
                  );
                }}
              >
                <FormField label="Name">
                  <Input name="name" placeholder="Upper bracket" />
                </FormField>
                <FormField label="Type">
                  <Select defaultValue="ROUND_ROBIN" name="type">
                    <option value="ROUND_ROBIN">Round robin</option>
                    <option value="SINGLE_ELIMINATION">Single elimination</option>
                    <option value="SWISS">Swiss</option>
                  </Select>
                </FormField>
                <FormField label="Team count">
                  <Input defaultValue={8} min={2} name="team_count" type="number" />
                </FormField>
                {rankings.length > 1 ? (
                  <FormField label="Ranking">
                    <Select defaultValue={rankings[0].id} name="ranking_id">
                      {rankings.map((ranking) => (
                        <option key={ranking.id} value={ranking.id}>
                          #{ranking.position}: win {ranking.win_points}, draw {ranking.draw_points},
                          loss {ranking.loss_points}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                ) : null}
                <div className="md:col-span-4">
                  <Button type="submit">Create stage item</Button>
                </div>
              </form>
              <div className="space-y-4">
                {stage.stage_items.map((stageItem) => (
                  <details
                    className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4"
                    key={stageItem.id}
                    open
                  >
                    <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
                      <div>
                        <Pill tone="accent">{stageItem.type_name}</Pill>
                        <h4 className="mt-3 text-xl font-semibold text-white">
                          {stageItem.name || stageItem.type_name}
                        </h4>
                        <p className="mt-1 text-sm text-zinc-400">{stageItemStatus(stageItem)}</p>
                      </div>
                    </summary>
                    <div className="mt-5 space-y-5">
                      <form
                        className="grid gap-4 md:grid-cols-[1fr_auto_auto]"
                        onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                          event.preventDefault();
                          const formData = new FormData(event.currentTarget);
                          await runAction(
                            setFlash,
                            async () => {
                              await OpenApi.updateStageItemApiTournamentsTournamentIdStageItemsStageItemIdPut(
                                {
                                  body: {
                                    name: String(formData.get('name') ?? ''),
                                    ranking_id: stageItem.ranking_id ?? 0,
                                  },
                                  path: {
                                    stage_item_id: stageItem.id,
                                    tournament_id: bundle.tournament.id,
                                  },
                                  throwOnError: true,
                                },
                              );
                            },
                            'Name saved.',
                            onRefresh,
                          );
                        }}
                      >
                        <Input
                          defaultValue={stageItem.name}
                          name="name"
                          placeholder="Stage item name"
                        />
                        <Button type="submit">Save name</Button>
                        <Button
                          onClick={async () => {
                            if (
                              !window.confirm(
                                `Delete stage item ${stageItem.name || stageItem.type_name}?`,
                              )
                            )
                              return;
                            await runAction(
                              setFlash,
                              async () => {
                                await OpenApi.deleteStageItemApiTournamentsTournamentIdStageItemsStageItemIdDelete(
                                  {
                                    path: {
                                      stage_item_id: stageItem.id,
                                      tournament_id: bundle.tournament.id,
                                    },
                                    throwOnError: true,
                                  },
                                );
                              },
                              'Stage item deleted successfully.',
                              onRefresh,
                            );
                          }}
                          tone="danger"
                          type="button"
                        >
                          Delete item
                        </Button>
                      </form>
                      <StageItemSlots
                        nextStageEntries={bundle.nextStageRankings[String(stageItem.id)]}
                        options={bundle.availableInputs[String(stage.id)] ?? []}
                        stageItem={stageItem}
                        stageItemsById={stageItemsById}
                        teamLookup={teamLookup}
                        tournamentId={bundle.tournament.id}
                      />
                      <Surface className="space-y-4 border-white/10 bg-white/5 p-4">
                        <h5 className="font-semibold text-white">Rounds</h5>
                        <StageItemRounds
                          stageItem={stageItem}
                          stageItemsById={stageItemsById}
                          tournamentId={bundle.tournament.id}
                        />
                      </Surface>
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
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}
