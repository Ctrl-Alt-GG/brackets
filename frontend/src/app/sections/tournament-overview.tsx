import type { FlattenedMatch, TournamentBundle } from '../types';
import * as OpenApi from '../../openapi';
import { inputLabel, formatDateTime } from '../utils';
import { Link } from 'react-router';
import { Pill, Surface } from '../ui';

export function OverviewSection({
  bundle,
  isAuthenticated,
  matches,
  stageItemsById,
  teamMap,
}: {
  bundle: TournamentBundle;
  isAuthenticated: boolean;
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teamMap: Map<number, OpenApi.FullTeamWithPlayers>;
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
      <div className="space-y-6">
        {isAuthenticated ? (
          <Surface className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
                  Upcoming
                </p>
                <h2 className="mt-2 font-display text-2xl font-semibold text-white">
                  Suggested next matches
                </h2>
              </div>
              <Pill>{`${bundle.upcomingMatches.length} options`}</Pill>
            </div>
            {bundle.upcomingMatches.length === 0 ? (
              <p className="text-sm text-zinc-300">No upcoming matches available right now.</p>
            ) : (
              <div className="grid gap-3">
                {bundle.upcomingMatches.slice(0, 12).map((entry, index) => (
                  <div
                    className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4"
                    key={`${entry.stageItemId}-${index}`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                          {entry.stageName} / {entry.stageItemName}
                        </p>
                        <h3 className="mt-2 text-lg font-semibold text-white">
                          {inputLabel(entry.suggestion.stage_item_input1, stageItemsById)} vs{' '}
                          {inputLabel(entry.suggestion.stage_item_input2, stageItemsById)}
                        </h3>
                      </div>
                      {entry.suggestion.is_recommended ? (
                        <Pill tone="success">recommended</Pill>
                      ) : (
                        <Pill>candidate</Pill>
                      )}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-zinc-400">
                      <span>ELO diff {entry.suggestion.elo_diff}</span>
                      <span>Swiss diff {entry.suggestion.swiss_diff}</span>
                      <span>Played together {entry.suggestion.times_played_sum}x</span>
                      <span>Behind schedule {entry.suggestion.player_behind_schedule_count}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Surface>
        ) : null}

        <Surface className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
              Competition setup
            </p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-white">
              Tournament structure
            </h2>
          </div>
          <div className="space-y-6">
            {bundle.stages.map((stage) => (
              <div className="space-y-4" key={stage.id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-xl font-semibold text-white">{stage.name}</h3>
                    <p className="text-sm text-zinc-400">
                      {stage.is_active ? 'Currently active stage.' : 'Inactive stage.'}
                    </p>
                  </div>
                  {stage.is_active ? <Pill tone="accent">active</Pill> : <Pill>queued</Pill>}
                </div>
                <div className="grid gap-4">
                  {stage.stage_items.map((stageItem) => (
                    <StageItemVisualization
                      key={stageItem.id}
                      stageItem={stageItem}
                      stageItemsById={stageItemsById}
                      teamMap={teamMap}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Surface>
      </div>

      <div className="space-y-6">
        <Surface className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
              Live feed
            </p>
            <h2 className="mt-2 font-display text-2xl font-semibold text-white">
              Scheduled matches
            </h2>
          </div>
          <div className="space-y-3">
            {matches.slice(0, 10).map(({ match, round, stage, stageItem }) => (
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
                  {formatDateTime(match.start_time)} · court{' '}
                  {match.court?.name ?? match.court_id ?? 'TBD'}
                </p>
              </div>
            ))}
          </div>
        </Surface>
        {isAuthenticated ? (
          <Surface className="space-y-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-brand-200">
                Quick routes
              </p>
              <h2 className="mt-2 font-display text-2xl font-semibold text-white">
                Management shortcuts
              </h2>
            </div>
            <div className="grid gap-3">
              <Link
                className="rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-3 text-sm font-semibold text-white transition hover:border-brand-300/40"
                to={`/tournaments/${bundle.tournament.id}/players`}
              >
                Player roster
              </Link>
              <Link
                className="rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-3 text-sm font-semibold text-white transition hover:border-brand-300/40"
                to={`/tournaments/${bundle.tournament.id}/teams`}
              >
                Team builder
              </Link>
              <Link
                className="rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-3 text-sm font-semibold text-white transition hover:border-brand-300/40"
                to={`/tournaments/${bundle.tournament.id}/schedule`}
              >
                Schedule lanes
              </Link>
              <Link
                className="rounded-[1.25rem] border border-white/10 bg-black/20 px-4 py-3 text-sm font-semibold text-white transition hover:border-brand-300/40"
                to={`/tournaments/${bundle.tournament.id}/stages`}
              >
                Stage editor
              </Link>
            </div>
          </Surface>
        ) : null}
      </div>
    </div>
  );
}

export function StageItemVisualization({
  stageItem,
  stageItemsById,
  teamMap,
}: {
  stageItem: OpenApi.StageItemWithRounds;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teamMap: Map<number, OpenApi.FullTeamWithPlayers>;
}) {
  const standings = [...stageItem.inputs]
    .filter((input) => input.team_id != null)
    .sort((left, right) => {
      if (left.wins !== right.wins) return right.wins - left.wins;
      if (left.draws !== right.draws) return right.draws - left.draws;
      if (left.losses !== right.losses) return left.losses - right.losses;
      return left.slot - right.slot;
    });

  return (
    <div className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="accent">{stageItem.type_name}</Pill>
            <Pill>{`${stageItem.team_count} slots`}</Pill>
          </div>
          <h4 className="mt-3 text-lg font-semibold text-white">
            {stageItem.name || stageItem.type_name}
          </h4>
        </div>
      </div>

      {stageItem.type === 'SINGLE_ELIMINATION' ? (
        <div className="mt-4 overflow-x-auto">
          <div className="flex min-w-max gap-4 pb-2">
            {stageItem.rounds.map((round) => (
              <div className="w-72 space-y-3" key={round.id}>
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">Bracket round</p>
                  <h5 className="mt-1 font-semibold text-white">{round.name}</h5>
                </div>
                {round.matches.map((match) => (
                  <div
                    className="rounded-[1.25rem] border border-white/10 bg-white/5 p-3"
                    key={match.id}
                  >
                    <div className="flex items-center justify-between gap-2 text-sm text-zinc-200">
                      <span>{inputLabel(match.stage_item_input1, stageItemsById)}</span>
                      <strong className="text-brand-200">{match.stage_item_input1_score}</strong>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2 text-sm text-zinc-200">
                      <span>{inputLabel(match.stage_item_input2, stageItemsById)}</span>
                      <strong className="text-brand-200">{match.stage_item_input2_score}</strong>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">Current table</p>
            <div className="space-y-2">
              {standings.length === 0 ? (
                <p className="text-sm text-zinc-400">No teams seeded yet.</p>
              ) : null}
              {standings.map((input) => {
                const team = input.team_id != null ? teamMap.get(input.team_id) : null;
                return (
                  <div
                    className="flex items-center justify-between rounded-[1rem] border border-white/10 bg-white/5 px-3 py-2 text-sm"
                    key={input.id}
                  >
                    <span className="font-medium text-white">
                      {team?.name ?? inputLabel(input, stageItemsById)}
                    </span>
                    <span className="text-zinc-400">
                      {input.wins}W / {input.draws}D / {input.losses}L
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">Round flow</p>
            <div className="grid gap-3">
              {stageItem.rounds.map((round) => (
                <div
                  className="rounded-[1.25rem] border border-white/10 bg-white/5 p-3"
                  key={round.id}
                >
                  <p className="text-sm font-semibold text-white">{round.name}</p>
                  <div className="mt-3 space-y-2 text-sm text-zinc-300">
                    {round.matches.map((match) => (
                      <div
                        className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-black/20 px-3 py-2"
                        key={match.id}
                      >
                        <span>
                          {inputLabel(match.stage_item_input1, stageItemsById)}{' '}
                          <strong className="text-brand-200">
                            {match.stage_item_input1_score}
                          </strong>
                        </span>
                        <span className="text-zinc-500">vs</span>
                        <span>
                          <strong className="text-brand-200">
                            {match.stage_item_input2_score}
                          </strong>{' '}
                          {inputLabel(match.stage_item_input2, stageItemsById)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
