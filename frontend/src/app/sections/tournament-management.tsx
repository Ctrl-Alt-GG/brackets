import type { FormEvent } from 'react';
import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import { runAction } from '../hooks';
import { DateTimeField } from '../components/date-time-field';
import { MatchCard } from '../components/match-card';
import { StageItemVisualization } from './tournament-overview';
import type { FlashMessage, FlattenedMatch, TournamentBundle } from '../types';
import {
  cx,
  formatDateTime,
  inputLabel,
  isScored,
  normalizeDashboardEndpoint,
  toCheckbox,
  toNumber,
  toOptionalNumber,
  toOptionalString,
} from '../utils';
import { Button, FormField, Input, Pill, Select, Surface, Textarea } from '../ui';

export function ScheduleSection({
  compact,
  courts,
  isAuthenticated,
  matches,
  onRefresh,
  setFlash,
  stageItemsById,
  tournamentId,
}: {
  compact?: boolean;
  courts: OpenApi.Court[];
  isAuthenticated: boolean;
  matches: FlattenedMatch[];
  onRefresh: () => void;
  setFlash: (message: FlashMessage) => void;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  tournamentId: number;
}) {
  const grouped = courts.map((court) => ({
    court,
    matches: matches.filter((entry) => entry.match.court_id === court.id),
  }));
  const unscheduled = matches.filter((entry) => entry.match.court_id == null);

  return (
    <div className="space-y-6">
      {!compact ? (
        <Surface className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
                Scheduler
              </p>
              <h2 className="mt-2 font-display text-2xl font-semibold text-white">Court lanes</h2>
            </div>
            {isAuthenticated ? (
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
                    'Scheduling completed successfully.',
                    onRefresh,
                  );
                }}
                type="button"
              >
                Schedule all matches
              </Button>
            ) : null}
          </div>
          {isAuthenticated ? (
            <form
              className="grid gap-4 rounded-[1.25rem] border border-white/10 bg-black/20 p-4 md:grid-cols-[1fr_auto]"
              onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                const formData = new FormData(event.currentTarget);
                await runAction(
                  setFlash,
                  async () => {
                    await OpenApi.createCourtApiTournamentsTournamentIdCourtsPost({
                      body: { name: String(formData.get('name') ?? '') },
                      path: { tournament_id: tournamentId },
                      throwOnError: true,
                    });
                  },
                  'Court created successfully.',
                  () => {
                    event.currentTarget.reset();
                    onRefresh();
                  },
                );
              }}
            >
              <Input name="name" placeholder="Add a new court or station" required />
              <Button tone="secondary" type="submit">
                Create court
              </Button>
            </form>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {courts.map((court) => (
              <details
                className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4"
                key={court.id}
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">Court</p>
                    <p className="mt-2 font-display text-2xl font-semibold text-white">
                      {court.name}
                    </p>
                  </div>
                  <Pill>#{court.id}</Pill>
                </summary>
                {isAuthenticated ? (
                  <form
                    className="mt-4 flex flex-col gap-3"
                    onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                      event.preventDefault();
                      const formData = new FormData(event.currentTarget);
                      await runAction(
                        setFlash,
                        async () => {
                          await OpenApi.updateCourtByIdApiTournamentsTournamentIdCourtsCourtIdPut({
                            body: { name: String(formData.get('name') ?? '') },
                            path: { court_id: court.id, tournament_id: tournamentId },
                            throwOnError: true,
                          });
                        },
                        'Court updated successfully.',
                        onRefresh,
                      );
                    }}
                  >
                    <Input defaultValue={court.name} name="name" />
                    <div className="flex gap-3">
                      <Button tone="secondary" type="submit">
                        Save
                      </Button>
                      <Button
                        onClick={async () => {
                          if (!window.confirm(`Delete court ${court.name}?`)) return;
                          await runAction(
                            setFlash,
                            async () => {
                              await OpenApi.deleteCourtApiTournamentsTournamentIdCourtsCourtIdDelete(
                                {
                                  path: { court_id: court.id, tournament_id: tournamentId },
                                  throwOnError: true,
                                },
                              );
                            },
                            'Court deleted successfully.',
                            onRefresh,
                          );
                        }}
                        tone="danger"
                        type="button"
                      >
                        Delete
                      </Button>
                    </div>
                  </form>
                ) : null}
              </details>
            ))}
          </div>
        </Surface>
      ) : null}
      <div className={cx('grid gap-4', compact ? 'xl:grid-cols-2' : 'xl:grid-cols-3')}>
        {grouped.map(({ court, matches: courtMatches }) => (
          <Surface className="space-y-4" key={court.id}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">Court</p>
                <h2
                  className={cx(
                    'font-display font-semibold text-white',
                    compact ? 'text-3xl' : 'text-2xl',
                  )}
                >
                  {court.name}
                </h2>
              </div>
              <Pill>{`${courtMatches.length} matches`}</Pill>
            </div>
            <div className="space-y-3">
              {courtMatches.length === 0 ? (
                <p className="text-sm text-zinc-400">No matches on this court yet.</p>
              ) : null}
              {courtMatches.map((entry) => {
                const { match, round, stage, stageItem } = entry;

                if (compact) {
                  return (
                    <MatchCard
                      entry={entry}
                      key={match.id}
                      size="lg"
                      stageItemsById={stageItemsById}
                    />
                  );
                }

                return (
                  <div
                    className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4"
                    key={match.id}
                  >
                    <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                      {stage.name} / {stageItem.name || stageItem.type_name} / {round.name}
                    </p>
                    <h3 className="mt-2 text-lg font-semibold text-white">
                      {inputLabel(match.stage_item_input1, stageItemsById)}{' '}
                      <span className="text-brand-300">{match.stage_item_input1_score}</span> -{' '}
                      <span className="text-brand-300">{match.stage_item_input2_score}</span>{' '}
                      {inputLabel(match.stage_item_input2, stageItemsById)}
                    </h3>
                    <p className="mt-2 text-sm text-zinc-400">
                      {formatDateTime(match.start_time)} · position{' '}
                      {match.position_in_schedule ?? 'TBD'}
                    </p>
                    {isAuthenticated ? (
                      <form
                        className="mt-4 grid gap-3 md:grid-cols-2"
                        onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                          event.preventDefault();
                          const formData = new FormData(event.currentTarget);
                          await runAction(
                            setFlash,
                            async () => {
                              await OpenApi.rescheduleMatchApiTournamentsTournamentIdMatchesMatchIdReschedulePost(
                                {
                                  body: {
                                    new_court_id: toNumber(formData.get('new_court_id')),
                                    new_position: toNumber(formData.get('new_position')),
                                    old_court_id: match.court_id ?? 0,
                                    old_position: match.position_in_schedule ?? 0,
                                  },
                                  path: { match_id: match.id, tournament_id: tournamentId },
                                  throwOnError: true,
                                },
                              );
                            },
                            'Match rescheduled successfully.',
                            onRefresh,
                          );
                        }}
                      >
                        <FormField label="Move to court id">
                          <Input
                            defaultValue={match.court_id ?? ''}
                            name="new_court_id"
                            type="number"
                          />
                        </FormField>
                        <FormField label="New position">
                          <Input
                            defaultValue={match.position_in_schedule ?? ''}
                            name="new_position"
                            type="number"
                          />
                        </FormField>
                        <div className="md:col-span-2">
                          <Button tone="secondary" type="submit">
                            Reschedule
                          </Button>
                        </div>
                      </form>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </Surface>
        ))}
        {!compact ? (
          <Surface className="space-y-4">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">Unscheduled</p>
              <h2 className="mt-2 font-display text-2xl font-semibold text-white">Waiting room</h2>
            </div>
            <div className="space-y-3">
              {unscheduled.length === 0 ? (
                <p className="text-sm text-zinc-400">All matches are scheduled.</p>
              ) : null}
              {unscheduled.map(({ match, round, stage, stageItem }) => (
                <div
                  className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4"
                  key={match.id}
                >
                  <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                    {stage.name} / {stageItem.name || stageItem.type_name} / {round.name}
                  </p>
                  <h3 className="mt-2 text-lg font-semibold text-white">
                    {inputLabel(match.stage_item_input1, stageItemsById)} vs{' '}
                    {inputLabel(match.stage_item_input2, stageItemsById)}
                  </h3>
                </div>
              ))}
            </div>
          </Surface>
        ) : null}
      </div>
    </div>
  );
}

export function StandingsSection({
  compact,
  rankings,
  standings,
}: {
  compact?: boolean;
  rankings: OpenApi.Ranking[];
  standings: OpenApi.FullTeamWithPlayers[];
}) {
  const rankedStandings = standings.map((team, index) => ({
    rank: index + 1,
    team,
  }));

  return (
    <div className="space-y-6">
      <Surface className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
              Who is winning
            </p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-white">Standings</h2>
          </div>
          <Pill>{`${standings.length} teams`}</Pill>
        </div>
        {compact ? (
          <div className="grid gap-3">
            {rankedStandings.length === 0 ? (
              <p className="text-sm text-zinc-400">No teams have been added yet.</p>
            ) : null}
            {rankedStandings.map(({ rank, team }) => (
              <div
                className="grid grid-cols-[auto_1fr_auto] items-center gap-4 rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-4"
                key={team.id}
              >
                <div className="min-w-12 text-center">
                  <p className="font-display text-3xl font-semibold text-white">{rank}</p>
                </div>
                <p className="font-display text-2xl font-semibold text-white">{team.name}</p>
                <p className="text-right text-lg text-zinc-300">
                  <span className="font-semibold text-emerald-300">{team.wins}</span> won ·{' '}
                  {team.draws} drawn · {team.losses} lost
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
                </tr>
              </thead>
              <tbody>
                {standings.length === 0 ? (
                  <tr>
                    <td className="px-3 py-6 text-sm text-zinc-400" colSpan={7}>
                      No teams have been added yet.
                    </td>
                  </tr>
                ) : null}
                {rankedStandings.map(({ rank, team }) => (
                  <tr className="border-b border-white/5" key={team.id}>
                    <td className="px-3 py-4 text-zinc-500">{rank}</td>
                    <td className="px-3 py-4 font-semibold text-white">{team.name}</td>
                    <td className="px-3 py-4 text-zinc-400">
                      {team.players.map((player) => player.name).join(', ') || '—'}
                    </td>
                    <td className="px-3 py-4">{team.wins + team.draws + team.losses}</td>
                    <td className="px-3 py-4">{team.wins}</td>
                    <td className="px-3 py-4">{team.draws}</td>
                    <td className="px-3 py-4">{team.losses}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Surface>
      {!compact ? (
        <Surface className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
              Scoring rules
            </p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-white">
              How points are awarded
            </h2>
          </div>
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
        </Surface>
      ) : null}
    </div>
  );
}

export function RankingsSection({
  bundle,
  onRefresh,
  setFlash,
  standings,
}: {
  bundle: TournamentBundle;
  onRefresh: () => void;
  setFlash: (message: FlashMessage) => void;
  standings: OpenApi.FullTeamWithPlayers[];
}) {
  return (
    <div className="space-y-6">
      <StandingsSection rankings={bundle.rankings} standings={standings} />
      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <Surface className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
              Create
            </p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-white">Ranking rule</h2>
          </div>
          <form
            className="space-y-4"
            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              const formData = new FormData(event.currentTarget);
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
                  event.currentTarget.reset();
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
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
                Rules
              </p>
              <h2 className="mt-2 font-display text-2xl font-semibold text-white">
                Ranking definitions
              </h2>
            </div>
            <Pill>{`${bundle.rankings.length} rankings`}</Pill>
          </div>
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
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
            Scoreboard
          </p>
          <h2 className="mt-2 font-display text-2xl font-semibold text-white">Latest results</h2>
        </div>
        <Pill>{`${scoredMatches.length} scored matches`}</Pill>
      </div>
      <div className="grid gap-3">
        {scoredMatches.map(({ match, round, stage, stageItem }) => (
          <div className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4" key={match.id}>
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
              {stage.name} / {stageItem.name || stageItem.type_name} / {round.name}
            </p>
            <h3 className="mt-2 text-xl font-semibold text-white">
              {inputLabel(match.stage_item_input1, stageItemsById)}{' '}
              <span className="text-brand-300">{match.stage_item_input1_score}</span> -{' '}
              <span className="text-brand-300">{match.stage_item_input2_score}</span>{' '}
              {inputLabel(match.stage_item_input2, stageItemsById)}
            </h3>
            <p className="mt-2 text-sm text-zinc-400">
              {formatDateTime(match.start_time)} · court{' '}
              {match.court?.name ?? match.court_id ?? 'TBD'}
            </p>
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
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
            Tournament settings
          </p>
          <h2 className="mt-2 font-display text-2xl font-semibold text-white">
            Metadata and policy
          </h2>
        </div>
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
                    auto_assign_courts: toCheckbox(formData.get('auto_assign_courts')),
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
          <FormField label="Duration minutes">
            <Input
              defaultValue={tournament.duration_minutes}
              name="duration_minutes"
              type="number"
            />
          </FormField>
          <FormField label="Margin minutes">
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
          <label className="md:col-span-2 flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
            <input
              className="h-4 w-4 accent-brand-500"
              defaultChecked={tournament.auto_assign_courts}
              name="auto_assign_courts"
              type="checkbox"
            />
            <span>Auto-assign courts when scheduling</span>
          </label>
          <div className="md:col-span-2">
            <Button type="submit">Save tournament</Button>
          </div>
        </form>
      </Surface>

      <Surface className="space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
            Lifecycle
          </p>
          <h2 className="mt-2 font-display text-2xl font-semibold text-white">
            Status and sharing
          </h2>
        </div>
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
  const stageItemsById = new Map<number, OpenApi.StageItemWithRounds>();
  bundle.stages.forEach((stage) =>
    stage.stage_items.forEach((item) => stageItemsById.set(item.id, item)),
  );

  return (
    <div className="space-y-6">
      <Surface className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
              Stages
            </p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-white">Bracket editor</h2>
          </div>
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
        </div>
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
              <Pill>#{stage.id}</Pill>
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
                      await OpenApi.updateStageApiTournamentsTournamentIdStagesStageIdPut({
                        body: { name: String(formData.get('name') ?? '') },
                        path: { stage_id: stage.id, tournament_id: bundle.tournament.id },
                        throwOnError: true,
                      });
                    },
                    'Stage updated successfully.',
                    onRefresh,
                  );
                }}
              >
                <Input defaultValue={stage.name} name="name" />
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
                  const formData = new FormData(event.currentTarget);
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
                      event.currentTarget.reset();
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
                <FormField label="Ranking id">
                  <Input name="ranking_id" placeholder="Optional" type="number" />
                </FormField>
                <div className="md:col-span-4">
                  <Button type="submit">Create stage item</Button>
                </div>
              </form>
              <div className="space-y-4">
                {stage.stage_items.map((stageItem) => (
                  <details
                    className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4"
                    key={stageItem.id}
                    open={focusStageItem?.id === stageItem.id}
                  >
                    <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Pill tone="accent">{stageItem.type_name}</Pill>
                          <Pill>{`${stageItem.rounds.length} rounds`}</Pill>
                        </div>
                        <h4 className="mt-3 text-xl font-semibold text-white">
                          {stageItem.name || stageItem.type_name}
                        </h4>
                      </div>
                      <Pill>#{stageItem.id}</Pill>
                    </summary>
                    <div className="mt-5 space-y-5">
                      <form
                        className="grid gap-4 md:grid-cols-[1fr_180px_auto_auto]"
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
                                    ranking_id: toNumber(formData.get('ranking_id')),
                                  },
                                  path: {
                                    stage_item_id: stageItem.id,
                                    tournament_id: bundle.tournament.id,
                                  },
                                  throwOnError: true,
                                },
                              );
                            },
                            'Stage item updated successfully.',
                            onRefresh,
                          );
                        }}
                      >
                        <Input
                          defaultValue={stageItem.name}
                          name="name"
                          placeholder="Stage item name"
                        />
                        <Input
                          defaultValue={stageItem.ranking_id ?? ''}
                          name="ranking_id"
                          placeholder="Ranking id"
                          type="number"
                        />
                        <Button type="submit">Save item</Button>
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
                      <div className="grid gap-4 lg:grid-cols-2">
                        <StageItemVisualization
                          stageItem={stageItem}
                          stageItemsById={stageItemsById}
                          teamMap={teamLookup}
                          tournamentId={bundle.tournament.id}
                        />
                        <Surface className="space-y-4 border-white/10 bg-white/5 p-4">
                          <div>
                            <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                              Slot inputs
                            </p>
                            <h5 className="mt-2 font-semibold text-white">Seeding and winners</h5>
                          </div>
                          <div className="space-y-3">
                            {stageItem.inputs.map((input) => {
                              const options = bundle.availableInputs[String(input.id)] ?? [];
                              const currentValue =
                                input.team_id != null
                                  ? `team:${input.team_id}`
                                  : input.winner_from_stage_item_id != null &&
                                      input.winner_position != null
                                    ? `winner:${input.winner_from_stage_item_id}:${input.winner_position}`
                                    : 'empty';
                              return (
                                <form
                                  className="grid gap-3 rounded-[1.25rem] border border-white/10 bg-black/20 p-3 md:grid-cols-[1fr_auto]"
                                  key={input.id}
                                  onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                                    event.preventDefault();
                                    const formData = new FormData(event.currentTarget);
                                    const mode = String(formData.get('assignment') ?? 'empty');

                                    let body:
                                      | OpenApi.StageItemInputUpdateBodyEmpty
                                      | OpenApi.StageItemInputUpdateBodyFinal
                                      | OpenApi.StageItemInputUpdateBodyTentative;
                                    if (mode === 'empty') {
                                      body = {
                                        team_id: null,
                                        winner_from_stage_item_id: null,
                                        winner_position: null,
                                      };
                                    } else if (mode.startsWith('team:')) {
                                      body = { team_id: Number(mode.split(':')[1]) };
                                    } else {
                                      const [, winnerStageItemId, winnerPosition] = mode.split(':');
                                      body = {
                                        winner_from_stage_item_id: Number(winnerStageItemId),
                                        winner_position: Number(winnerPosition),
                                      };
                                    }

                                    await runAction(
                                      setFlash,
                                      async () => {
                                        await OpenApi.updateStageItemInputApiTournamentsTournamentIdStageItemsStageItemIdInputsStageItemInputIdPut(
                                          {
                                            body,
                                            path: {
                                              stage_item_id: stageItem.id,
                                              stage_item_input_id: input.id,
                                              tournament_id: bundle.tournament.id,
                                            },
                                            throwOnError: true,
                                          },
                                        );
                                      },
                                      'Stage item input updated successfully.',
                                      onRefresh,
                                    );
                                  }}
                                >
                                  <div>
                                    <p className="text-sm font-semibold text-white">
                                      Slot {input.slot}
                                    </p>
                                    <p className="mt-1 text-sm text-zinc-400">
                                      Current: {inputLabel(input, stageItemsById)}
                                    </p>
                                  </div>
                                  <div className="flex flex-wrap gap-3 md:justify-end">
                                    <Select defaultValue={currentValue} name="assignment">
                                      <option value="empty">Open slot</option>
                                      {options.map((option, optionIndex) => {
                                        if ('team_id' in option) {
                                          const team = teamLookup.get(option.team_id);
                                          return (
                                            <option
                                              key={`team-${option.team_id}-${optionIndex}`}
                                              value={`team:${option.team_id}`}
                                            >
                                              {team?.name ?? `Team #${option.team_id}`}
                                              {option.already_taken ? ' (taken)' : ''}
                                            </option>
                                          );
                                        }
                                        const source = stageItemsById.get(
                                          option.winner_from_stage_item_id,
                                        );
                                        return (
                                          <option
                                            key={`winner-${option.winner_from_stage_item_id}-${option.winner_position}-${optionIndex}`}
                                            value={`winner:${option.winner_from_stage_item_id}:${option.winner_position}`}
                                          >
                                            Winner of{' '}
                                            {source?.name ||
                                              source?.type_name ||
                                              `item #${option.winner_from_stage_item_id}`}{' '}
                                            slot {option.winner_position}
                                            {option.already_taken ? ' (taken)' : ''}
                                          </option>
                                        );
                                      })}
                                    </Select>
                                    <Button tone="secondary" type="submit">
                                      Assign
                                    </Button>
                                  </div>
                                </form>
                              );
                            })}
                          </div>
                        </Surface>
                      </div>
                      <div className="grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
                        <Surface className="space-y-4 border-white/10 bg-white/5 p-4">
                          <div>
                            <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                              Round controls
                            </p>
                            <h5 className="mt-2 font-semibold text-white">Round flow</h5>
                          </div>
                          <form
                            className="space-y-4"
                            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                              event.preventDefault();
                              const formData = new FormData(event.currentTarget);
                              await runAction(
                                setFlash,
                                async () => {
                                  await OpenApi.createRoundApiTournamentsTournamentIdRoundsPost({
                                    body: {
                                      name: toOptionalString(formData.get('name')),
                                      stage_item_id: stageItem.id,
                                    },
                                    path: { tournament_id: bundle.tournament.id },
                                    throwOnError: true,
                                  });
                                },
                                'Round created successfully.',
                                () => {
                                  event.currentTarget.reset();
                                  onRefresh();
                                },
                              );
                            }}
                          >
                            <FormField label="Create round">
                              <Input name="name" placeholder="Quarter finals" />
                            </FormField>
                            <Button tone="secondary" type="submit">
                              Create round
                            </Button>
                          </form>
                          <form
                            className="space-y-4"
                            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                              event.preventDefault();
                              const formData = new FormData(event.currentTarget);
                              await runAction(
                                setFlash,
                                async () => {
                                  await OpenApi.startNextRoundApiTournamentsTournamentIdStageItemsStageItemIdStartNextRoundPost(
                                    {
                                      body: {
                                        adjust_to_time:
                                          toOptionalString(formData.get('adjust_to_time')) ?? null,
                                      },
                                      path: {
                                        stage_item_id: stageItem.id,
                                        tournament_id: bundle.tournament.id,
                                      },
                                      throwOnError: true,
                                    },
                                  );
                                },
                                'Started next round successfully.',
                                onRefresh,
                              );
                            }}
                          >
                            <FormField label="Adjust to time before advancing">
                              <DateTimeField name="adjust_to_time" />
                            </FormField>
                            <Button tone="ghost" type="submit">
                              Start next round
                            </Button>
                          </form>
                          {bundle.nextStageRankings[String(stageItem.id)] ? (
                            <div className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4">
                              <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                                Next-stage ranking view
                              </p>
                              <div className="mt-3 space-y-2 text-sm text-zinc-200">
                                {bundle.nextStageRankings[String(stageItem.id)].map((entry) => (
                                  <div
                                    className="flex items-center justify-between"
                                    key={entry.stage_item_input.id}
                                  >
                                    <span>{entry.team.name}</span>
                                    <span className="text-zinc-400">
                                      slot {entry.stage_item_input.slot}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : null}
                        </Surface>
                        <div className="space-y-4">
                          {stageItem.rounds.map((round) => (
                            <details
                              className="rounded-[1.5rem] border border-white/10 bg-white/5 p-4"
                              key={round.id}
                              open
                            >
                              <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
                                <div>
                                  <h5 className="text-lg font-semibold text-white">{round.name}</h5>
                                  <p className="text-sm text-zinc-400">
                                    {round.matches.length} matches ·{' '}
                                    {round.is_draft ? 'draft' : 'official'}
                                  </p>
                                </div>
                                <Pill>{round.is_draft ? 'draft' : 'live'}</Pill>
                              </summary>
                              <div className="mt-4 space-y-4">
                                <form
                                  className="grid gap-4 rounded-[1.25rem] border border-white/10 bg-black/20 p-4 md:grid-cols-[1fr_auto_auto]"
                                  onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                                    event.preventDefault();
                                    const formData = new FormData(event.currentTarget);
                                    await runAction(
                                      setFlash,
                                      async () => {
                                        await OpenApi.updateRoundByIdApiTournamentsTournamentIdRoundsRoundIdPut(
                                          {
                                            body: {
                                              is_draft: toCheckbox(formData.get('is_draft')),
                                              name: String(formData.get('name') ?? ''),
                                            },
                                            path: {
                                              round_id: round.id,
                                              tournament_id: bundle.tournament.id,
                                            },
                                            throwOnError: true,
                                          },
                                        );
                                      },
                                      'Round updated successfully.',
                                      onRefresh,
                                    );
                                  }}
                                >
                                  <Input defaultValue={round.name} name="name" />
                                  <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-200">
                                    <input
                                      className="h-4 w-4 accent-brand-500"
                                      defaultChecked={round.is_draft}
                                      name="is_draft"
                                      type="checkbox"
                                    />
                                    <span>Draft round</span>
                                  </label>
                                  <div className="flex gap-3">
                                    <Button type="submit">Save round</Button>
                                    <Button
                                      onClick={async () => {
                                        if (!window.confirm(`Delete round ${round.name}?`)) return;
                                        await runAction(
                                          setFlash,
                                          async () => {
                                            await OpenApi.deleteRoundApiTournamentsTournamentIdRoundsRoundIdDelete(
                                              {
                                                path: {
                                                  round_id: round.id,
                                                  tournament_id: bundle.tournament.id,
                                                },
                                                throwOnError: true,
                                              },
                                            );
                                          },
                                          'Round deleted successfully.',
                                          onRefresh,
                                        );
                                      }}
                                      tone="danger"
                                      type="button"
                                    >
                                      Delete round
                                    </Button>
                                  </div>
                                </form>
                                <form
                                  className="grid gap-4 rounded-[1.25rem] border border-white/10 bg-black/20 p-4 md:grid-cols-2"
                                  onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                                    event.preventDefault();
                                    const formData = new FormData(event.currentTarget);
                                    await runAction(
                                      setFlash,
                                      async () => {
                                        await OpenApi.createMatchApiTournamentsTournamentIdMatchesPost(
                                          {
                                            body: {
                                              court_id: toOptionalNumber(formData.get('court_id')),
                                              round_id: round.id,
                                              stage_item_input1_id: toOptionalNumber(
                                                formData.get('stage_item_input1_id'),
                                              ),
                                              stage_item_input1_winner_from_match_id:
                                                toOptionalNumber(
                                                  formData.get(
                                                    'stage_item_input1_winner_from_match_id',
                                                  ),
                                                ),
                                              stage_item_input2_id: toOptionalNumber(
                                                formData.get('stage_item_input2_id'),
                                              ),
                                              stage_item_input2_winner_from_match_id:
                                                toOptionalNumber(
                                                  formData.get(
                                                    'stage_item_input2_winner_from_match_id',
                                                  ),
                                                ),
                                            },
                                            path: { tournament_id: bundle.tournament.id },
                                            throwOnError: true,
                                          },
                                        );
                                      },
                                      'Match created successfully.',
                                      () => {
                                        event.currentTarget.reset();
                                        onRefresh();
                                      },
                                    );
                                  }}
                                >
                                  <FormField label="Input 1 slot id">
                                    <Input
                                      name="stage_item_input1_id"
                                      placeholder="Optional slot id"
                                      type="number"
                                    />
                                  </FormField>
                                  <FormField label="Input 2 slot id">
                                    <Input
                                      name="stage_item_input2_id"
                                      placeholder="Optional slot id"
                                      type="number"
                                    />
                                  </FormField>
                                  <FormField label="Input 1 winner from match id">
                                    <Input
                                      name="stage_item_input1_winner_from_match_id"
                                      placeholder="Optional match id"
                                      type="number"
                                    />
                                  </FormField>
                                  <FormField label="Input 2 winner from match id">
                                    <Input
                                      name="stage_item_input2_winner_from_match_id"
                                      placeholder="Optional match id"
                                      type="number"
                                    />
                                  </FormField>
                                  <FormField label="Court id">
                                    <Input
                                      name="court_id"
                                      placeholder="Optional court id"
                                      type="number"
                                    />
                                  </FormField>
                                  <div className="md:col-span-2">
                                    <Button tone="secondary" type="submit">
                                      Create match
                                    </Button>
                                  </div>
                                </form>
                                <div className="space-y-3">
                                  {round.matches.map((match) => (
                                    <details
                                      className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4"
                                      key={match.id}
                                    >
                                      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3">
                                        <div>
                                          <h6 className="text-base font-semibold text-white">
                                            {inputLabel(match.stage_item_input1, stageItemsById)}{' '}
                                            {match.stage_item_input1_score} -{' '}
                                            {match.stage_item_input2_score}{' '}
                                            {inputLabel(match.stage_item_input2, stageItemsById)}
                                          </h6>
                                          <p className="text-sm text-zinc-400">
                                            {formatDateTime(match.start_time)} · court{' '}
                                            {match.court?.name ?? match.court_id ?? 'TBD'}
                                          </p>
                                        </div>
                                        <Pill>{match.position_in_schedule ?? '—'}</Pill>
                                      </summary>
                                      <form
                                        className="mt-4 grid gap-4 md:grid-cols-3"
                                        onSubmit={async (event: FormEvent<HTMLFormElement>) => {
                                          event.preventDefault();
                                          const formData = new FormData(event.currentTarget);
                                          await runAction(
                                            setFlash,
                                            async () => {
                                              await OpenApi.updateMatchByIdApiTournamentsTournamentIdMatchesMatchIdPut(
                                                {
                                                  body: {
                                                    court_id: toOptionalNumber(
                                                      formData.get('court_id'),
                                                    ),
                                                    custom_duration_minutes: toOptionalNumber(
                                                      formData.get('custom_duration_minutes'),
                                                    ),
                                                    custom_margin_minutes: toOptionalNumber(
                                                      formData.get('custom_margin_minutes'),
                                                    ),
                                                    round_id: toNumber(formData.get('round_id')),
                                                    stage_item_input1_score: toNumber(
                                                      formData.get('stage_item_input1_score'),
                                                    ),
                                                    stage_item_input2_score: toNumber(
                                                      formData.get('stage_item_input2_score'),
                                                    ),
                                                  },
                                                  path: {
                                                    match_id: match.id,
                                                    tournament_id: bundle.tournament.id,
                                                  },
                                                  throwOnError: true,
                                                },
                                              );
                                            },
                                            'Match updated successfully.',
                                            onRefresh,
                                          );
                                        }}
                                      >
                                        <FormField label="Round id">
                                          <Input
                                            defaultValue={match.round_id}
                                            name="round_id"
                                            type="number"
                                          />
                                        </FormField>
                                        <FormField label="Court id">
                                          <Input
                                            defaultValue={match.court_id ?? ''}
                                            name="court_id"
                                            type="number"
                                          />
                                        </FormField>
                                        <FormField label="Custom duration minutes">
                                          <Input
                                            defaultValue={match.custom_duration_minutes ?? ''}
                                            name="custom_duration_minutes"
                                            type="number"
                                          />
                                        </FormField>
                                        <FormField label="Custom margin minutes">
                                          <Input
                                            defaultValue={match.custom_margin_minutes ?? ''}
                                            name="custom_margin_minutes"
                                            type="number"
                                          />
                                        </FormField>
                                        <FormField label="Score 1">
                                          <Input
                                            defaultValue={match.stage_item_input1_score}
                                            name="stage_item_input1_score"
                                            type="number"
                                          />
                                        </FormField>
                                        <FormField label="Score 2">
                                          <Input
                                            defaultValue={match.stage_item_input2_score}
                                            name="stage_item_input2_score"
                                            type="number"
                                          />
                                        </FormField>
                                        <div className="md:col-span-3 flex flex-wrap gap-3">
                                          <Button type="submit">Save match</Button>
                                          <Button
                                            onClick={async () => {
                                              if (!window.confirm(`Delete match #${match.id}?`))
                                                return;
                                              await runAction(
                                                setFlash,
                                                async () => {
                                                  await OpenApi.deleteMatchApiTournamentsTournamentIdMatchesMatchIdDelete(
                                                    {
                                                      path: {
                                                        match_id: match.id,
                                                        tournament_id: bundle.tournament.id,
                                                      },
                                                      throwOnError: true,
                                                    },
                                                  );
                                                },
                                                'Match deleted successfully.',
                                                onRefresh,
                                              );
                                            }}
                                            tone="danger"
                                            type="button"
                                          >
                                            Delete match
                                          </Button>
                                        </div>
                                      </form>
                                    </details>
                                  ))}
                                </div>
                              </div>
                            </details>
                          ))}
                        </div>
                      </div>
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
