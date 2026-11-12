import { Link } from 'react-router';

import * as OpenApi from '../../openapi';
import { TeamLink } from '../components/team-link';
import { useTournamentContext } from '../tournament-context';
import type { TournamentBundle } from '../types';
import {
  cx,
  formatPoints,
  formatScoreDifference,
  isBracket,
  pointsLabel,
  pointsPhrase,
  stageItemStandings,
} from '../utils';
import { Surface, SurfaceHeading } from '../ui';

/** How the teams of a group earn their place, in a few words next to its table. */
function pointsRule(stageItem: OpenApi.StageItemWithRounds, rankings: OpenApi.Ranking[]) {
  if (stageItem.type === 'SWISS') {
    return 'ranked by a rating that starts at 1200 and moves with every result';
  }

  const ranking = rankings.find((candidate) => candidate.id === stageItem.ranking_id);
  if (!ranking) return 'ranked by points';
  const rule = `win ${formatPoints(ranking.win_points)}, draw ${formatPoints(ranking.draw_points)}, loss ${formatPoints(ranking.loss_points)}`;
  return ranking.add_score_points ? `${rule}, plus the score of every match` : rule;
}

function ColumnHeading({ long, short }: { long: string; short: string }) {
  return (
    <th>
      <abbr className="no-underline sm:hidden" title={long}>
        {short}
      </abbr>
      <span className="hidden sm:inline">{long}</span>
    </th>
  );
}

export function StandingsSection({
  bigScreenPath,
  compact,
  rankings,
  stages,
  standings,
  teamMap,
}: {
  bigScreenPath?: string;
  compact?: boolean;
  rankings: OpenApi.Ranking[];
  stages: OpenApi.StageWithStageItems[];
  standings: TournamentBundle['standings'];
  teamMap: Map<number, OpenApi.FullTeamWithPlayers>;
}) {
  const { myTeamId } = useTournamentContext();
  // Results are kept per stage item, and teams only compete for a place within their own group.
  // Knockout brackets have no table: the Bracket page shows them.
  const tables = stages.flatMap((stage) =>
    stage.stage_items
      .filter((stageItem) => !isBracket(stageItem))
      .map((stageItem) => ({ entries: stageItemStandings(stageItem, standings), stage, stageItem }))
      .filter(({ entries }) => entries.length > 0),
  );

  return (
    <div className="space-y-6">
      <Surface>
        <SurfaceHeading
          actions={
            bigScreenPath ? (
              <Link className="btn btn-ghost btn-sm" to={bigScreenPath}>
                Big screen
              </Link>
            ) : null
          }
          title="Standings"
        />
        {tables.length === 0 ? (
          <p className="text-sm text-base-content/70">
            No standings yet: no team has joined a group.
          </p>
        ) : null}
        {tables.map(({ entries, stage, stageItem }) => (
          <section
            className="scroll-mt-6 space-y-3"
            id={`stage-item-${stageItem.id}`}
            key={stageItem.id}
          >
            <div>
              <h3 className="text-lg font-semibold">{stageItem.name || stageItem.type_name}</h3>
              <p className="text-sm text-base-content/70">
                {stage.name} · {stageItem.type_name}
                {compact ? null : ` · ${pointsRule(stageItem, rankings)}`}
              </p>
            </div>
            {compact ? (
              <div className="grid gap-3">
                {entries.map(({ input, standing }, index) => (
                  <div
                    className={cx(
                      'grid grid-cols-[auto_1fr_auto] items-center gap-4 rounded-box border bg-base-100/60 px-4 py-4',
                      input.team_id === myTeamId ? 'border-accent/60' : 'border-base-300',
                    )}
                    key={input.id}
                  >
                    <p className="min-w-12 text-center font-display text-3xl font-semibold">
                      {index + 1}
                    </p>
                    <p className="font-display text-2xl font-semibold">{input.team.name}</p>
                    <p className="text-right text-lg text-base-content/80">
                      <span className="font-semibold text-success">{standing.wins}</span> won ·{' '}
                      {standing.draws} drawn · {standing.losses} lost ·{' '}
                      <span className="font-semibold text-base-content">
                        {pointsPhrase(stageItem, standing.points)}
                      </span>
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Team</th>
                      <th className="hidden md:table-cell">Players</th>
                      <ColumnHeading long="Played" short="P" />
                      <ColumnHeading long="Won" short="W" />
                      <ColumnHeading long="Drawn" short="D" />
                      <ColumnHeading long="Lost" short="L" />
                      <th title="Score difference">+/−</th>
                      <th>{pointsLabel(stageItem)}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map(({ input, standing }, index) => (
                      <tr
                        className={cx(input.team_id === myTeamId && 'bg-accent/10')}
                        key={input.id}
                      >
                        <td className="text-base-content/70">{index + 1}</td>
                        <td className="font-semibold">
                          <TeamLink teamId={input.team_id}>{input.team.name}</TeamLink>
                        </td>
                        <td className="hidden text-base-content/70 md:table-cell">
                          {teamMap
                            .get(input.team_id)
                            ?.players.map((player) => player.name)
                            .join(', ') || '—'}
                        </td>
                        <td>{standing.wins + standing.draws + standing.losses}</td>
                        <td>{standing.wins}</td>
                        <td>{standing.draws}</td>
                        <td>{standing.losses}</td>
                        <td
                          title={`${standing.score_for} scored, ${standing.score_against} conceded`}
                        >
                          {formatScoreDifference(standing)}
                        </td>
                        <td className="font-semibold">{formatPoints(standing.points)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ))}
      </Surface>
      {!compact && tables.length > 0 ? (
        <p className="px-1 text-sm text-base-content/70">
          Teams with the same points are ranked by score difference, then by their total score, then
          by the number of wins, and after that by their seeding. Teams go through to the next stage
          in this order.
        </p>
      ) : null}
    </div>
  );
}
