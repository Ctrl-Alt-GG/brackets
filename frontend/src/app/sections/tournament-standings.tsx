import type { TFunction } from 'i18next';
import { Trans, useTranslation } from 'react-i18next';

import * as OpenApi from '../../openapi';
import { BigScreenLink } from '../components/big-screen';
import { TeamLink } from '../components/team-link';
import { useTournamentContext } from '../tournament-context';
import type { TournamentBundle } from '../types';
import { formatPoints, formatScoreDifference, pointsLabel, pointsPhrase } from '../format';
import { isBracket, stageItemName, stageItemStandings, stageName, stageTypeName } from '../matches';
import { cx } from '../utils';
import { Surface, SurfaceHeading } from '../ui';

/** How the teams of a group earn their place, in a few words next to its table. */
function pointsRule(
  stageItem: OpenApi.StageItemWithRounds,
  rankings: OpenApi.Ranking[],
  t: TFunction,
) {
  if (stageItem.type === 'SWISS') return t('standings.swissRule');

  const ranking = rankings.find((candidate) => candidate.id === stageItem.ranking_id);
  if (!ranking) return t('standings.pointsRule');
  const points = {
    draw: formatPoints(ranking.draw_points),
    loss: formatPoints(ranking.loss_points),
    win: formatPoints(ranking.win_points),
  };
  return ranking.add_score_points
    ? t('standings.ruleWithScores', points)
    : t('standings.rule', points);
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
  teamMap: Map<number, OpenApi.TournamentTeamWithPlayers>;
}) {
  const { t } = useTranslation();
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
          actions={bigScreenPath ? <BigScreenLink to={bigScreenPath} /> : null}
          title={t('tournament.standings')}
        />
        {tables.length === 0 ? (
          <p className="text-sm text-base-content/70">{t('standings.none')}</p>
        ) : null}
        {tables.map(({ entries, stage, stageItem }) => (
          <section
            className="scroll-mt-6 space-y-3"
            id={`stage-item-${stageItem.id}`}
            key={stageItem.id}
          >
            <div>
              <h3 className="text-lg font-semibold">{stageItemName(stageItem, t)}</h3>
              <p className="text-sm text-base-content/70">
                {stageName(stage, t)} · {stageTypeName(stageItem, t)}
                {compact ? null : ` · ${pointsRule(stageItem, rankings, t)}`}
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
                      <Trans
                        components={{ wins: <span className="font-semibold text-success" /> }}
                        i18nKey="standings.compactRecord"
                        values={{
                          draws: standing.draws,
                          losses: standing.losses,
                          wins: standing.wins,
                        }}
                      />{' '}
                      ·{' '}
                      <span className="font-semibold text-base-content">
                        {pointsPhrase(stageItem, standing.points, t)}
                      </span>
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="overflow-x-auto">
                {/* Narrow cells on phones, so that the points don't end up off-screen. */}
                <table className="table [&_td]:px-2 [&_th]:px-2 sm:[&_td]:px-4 sm:[&_th]:px-4">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{t('standings.team')}</th>
                      <th className="hidden md:table-cell">{t('standings.players')}</th>
                      <ColumnHeading
                        long={t('standings.played')}
                        short={t('standings.playedShort')}
                      />
                      <ColumnHeading long={t('standings.won')} short={t('standings.wonShort')} />
                      <ColumnHeading
                        long={t('standings.drawn')}
                        short={t('standings.drawnShort')}
                      />
                      <ColumnHeading long={t('standings.lost')} short={t('standings.lostShort')} />
                      <th title={t('standings.scoreDifference')}>+/−</th>
                      <th>{pointsLabel(stageItem, t)}</th>
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
                          title={t('standings.scores', {
                            conceded: standing.score_against,
                            scored: standing.score_for,
                          })}
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
        <p className="px-1 text-sm text-base-content/70">{t('standings.tiebreaks')}</p>
      ) : null}
    </div>
  );
}
