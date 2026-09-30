import type { FlattenedMatch, TournamentBundle } from '../types';
import * as OpenApi from '../../openapi';
import { toBracketViewerData } from '../bracket-adapter';
import { BracketViewer } from '../components/bracket-viewer';
import { MatchCard } from '../components/match-card';
import { cx, inputLabel, isScored, matchStatus, matchWinner, type MatchOutcome } from '../utils';
import { Link } from 'react-router';
import { Pill, Surface, SurfaceHeading } from '../ui';

function SectionHeading({ title }: { title: string }) {
  return <SurfaceHeading title={title} />;
}

export function OverviewSection({
  bundle,
  isAuthenticated,
  matches,
  stageItemsById,
  tournamentKey,
}: {
  bundle: TournamentBundle;
  isAuthenticated: boolean;
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  tournamentKey: string;
}) {
  const live = matches.filter((entry) => matchStatus(entry.match) === 'live');
  const upcoming = matches.filter((entry) => matchStatus(entry.match) === 'scheduled').slice(0, 6);
  const finished = matches.filter((entry) => matchStatus(entry.match) === 'finished').slice(-6);

  return (
    <div className="space-y-6">
      <Surface className="space-y-4">
        <SectionHeading title={live.length > 0 ? 'Playing now' : 'Coming up next'} />
        {live.length === 0 && upcoming.length === 0 ? (
          <p className="text-sm text-zinc-400">
            No matches are running or scheduled at the moment.
          </p>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(live.length > 0 ? live : upcoming).map((entry) => (
            <MatchCard entry={entry} key={entry.match.id} stageItemsById={stageItemsById} />
          ))}
        </div>
        {live.length > 0 && upcoming.length > 0 ? (
          <>
            <p className="pt-2 text-sm font-medium text-zinc-300">Coming up next</p>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {upcoming.map((entry) => (
                <MatchCard entry={entry} key={entry.match.id} stageItemsById={stageItemsById} />
              ))}
            </div>
          </>
        ) : null}
      </Surface>

      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <Surface className="space-y-4">
          <SectionHeading title="Stages and groups" />
          {bundle.stages.length === 0 ? (
            <p className="text-sm text-zinc-400">The tournament format has not been set up yet.</p>
          ) : null}
          <div className="space-y-5">
            {bundle.stages.map((stage) => (
              <div className="space-y-3" key={stage.id}>
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className="text-lg font-semibold text-white">{stage.name}</h3>
                  {stage.is_active ? <Pill tone="accent">happening now</Pill> : null}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {stage.stage_items.map((stageItem) => {
                    const stageItemMatches = stageItem.rounds.flatMap((round) => round.matches);
                    const played = stageItemMatches.filter(isScored).length;

                    return (
                      <Link
                        className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4 transition hover:border-brand-300/40"
                        key={stageItem.id}
                        to={`/tournaments/${tournamentKey}/dashboard/bracket`}
                      >
                        <p className="text-xs text-zinc-500">{stageItem.type_name}</p>
                        <h4 className="mt-2 font-semibold text-white">
                          {stageItem.name || stageItem.type_name}
                        </h4>
                        <p className="mt-2 text-sm text-zinc-400">
                          {stageItem.team_count} teams · {played} of {stageItemMatches.length}{' '}
                          matches played
                        </p>
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </Surface>

        <div className="space-y-6">
          <Surface className="space-y-4">
            <SectionHeading title="Latest results" />
            {finished.length === 0 ? (
              <p className="text-sm text-zinc-400">No results yet.</p>
            ) : (
              <div className="space-y-3">
                {finished.map((entry) => (
                  <MatchCard entry={entry} key={entry.match.id} stageItemsById={stageItemsById} />
                ))}
              </div>
            )}
          </Surface>

          {isAuthenticated ? (
            <Surface className="space-y-3">
              <SectionHeading title="Manage this tournament" />
              <div className="grid gap-2">
                {[
                  ['players', 'Players'],
                  ['teams', 'Teams'],
                  ['schedule', 'Schedule'],
                  ['stages', 'Format'],
                ].map(([suffix, label]) => (
                  <Link
                    className="rounded-[1rem] border border-white/10 bg-black/20 px-4 py-2.5 text-sm font-semibold text-white transition hover:border-brand-300/40"
                    key={suffix}
                    to={`/tournaments/${bundle.tournament.id}/${suffix}`}
                  >
                    {label}
                  </Link>
                ))}
              </div>
            </Surface>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Same emphasis as the match cards: the winner stands out, the loser recedes. */
function sideClass(winner: MatchOutcome, side: 1 | 2) {
  if (winner === side) return 'font-semibold text-white';
  if (winner === 1 || winner === 2) return 'text-zinc-500';
  return 'text-zinc-200';
}

export function StageItemVisualization({
  showMatches = true,
  stageItem,
  stageItemsById,
  teamMap,
  tournamentId,
}: {
  showMatches?: boolean;
  stageItem: OpenApi.StageItemWithRounds;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teamMap: Map<number, OpenApi.FullTeamWithPlayers>;
  tournamentId: number;
}) {
  const standings = [...stageItem.inputs]
    .filter((input) => input.team_id != null)
    .sort((left, right) => {
      if (left.wins !== right.wins) return right.wins - left.wins;
      if (left.draws !== right.draws) return right.draws - left.draws;
      if (left.losses !== right.losses) return left.losses - right.losses;
      return left.slot - right.slot;
    });
  const bracketData =
    stageItem.type === 'SINGLE_ELIMINATION'
      ? toBracketViewerData(stageItem, stageItemsById, tournamentId)
      : null;

  return (
    <div className="rounded-[1.5rem] border border-white/10 bg-black/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-lg font-semibold text-white">
            {stageItem.name || stageItem.type_name}
          </h4>
          <p className="mt-1 text-sm text-zinc-400">
            {stageItem.type_name} · {stageItem.team_count} teams
          </p>
        </div>
      </div>

      {stageItem.type === 'SINGLE_ELIMINATION' ? (
        <div className="mt-4">
          {bracketData ? (
            <BracketViewer data={bracketData} />
          ) : (
            <p className="text-sm text-zinc-400">
              The bracket appears here once the matches have been drawn.
            </p>
          )}
        </div>
      ) : (
        <div className={cx('mt-4 grid gap-4', showMatches && 'lg:grid-cols-[0.9fr_1.1fr]')}>
          <div className="space-y-3">
            <p className="text-sm font-medium text-zinc-300">Table</p>
            <div className="space-y-2">
              {standings.length === 0 ? (
                <p className="text-sm text-zinc-400">No teams have been added yet.</p>
              ) : null}
              {standings.map((input, index) => {
                const team = input.team_id != null ? teamMap.get(input.team_id) : null;
                return (
                  <div
                    className="flex items-center justify-between gap-3 rounded-[1rem] border border-white/10 bg-white/5 px-3 py-2 text-sm"
                    key={input.id}
                  >
                    <span className="flex items-center gap-3">
                      <span className="w-5 text-zinc-500">{index + 1}</span>
                      <span className="font-medium text-white">
                        {team?.name ?? inputLabel(input, stageItemsById)}
                      </span>
                    </span>
                    <span className="text-zinc-400">
                      {input.wins} won · {input.draws} drawn · {input.losses} lost
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          {showMatches ? (
            <div className="space-y-3">
              <p className="text-sm font-medium text-zinc-300">Matches</p>
              {/* Equal team columns keep "vs" in the middle of every row, and sharing one grid
                  between all rounds keeps it in a straight line even next to wider scores. */}
              <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-3">
                {stageItem.rounds.map((round) => (
                  <div
                    className="col-span-3 grid grid-cols-subgrid gap-y-2 rounded-[1.25rem] border border-white/10 bg-white/5 p-3"
                    key={round.id}
                  >
                    <p className="col-span-3 text-sm font-semibold text-white">{round.name}</p>
                    {round.matches.map((match) => {
                      const winner = matchWinner(match);
                      return (
                        <div
                          className="col-span-3 grid grid-cols-subgrid items-center rounded-xl bg-black/20 px-3 py-2 text-sm"
                          key={match.id}
                        >
                          <span className={cx('break-words text-right', sideClass(winner, 1))}>
                            {inputLabel(match.stage_item_input1, stageItemsById)}
                          </span>
                          <span className="text-center font-semibold tabular-nums text-white">
                            {isScored(match)
                              ? `${match.stage_item_input1_score} – ${match.stage_item_input2_score}`
                              : 'vs'}
                          </span>
                          <span className={cx('break-words', sideClass(winner, 2))}>
                            {inputLabel(match.stage_item_input2, stageItemsById)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
