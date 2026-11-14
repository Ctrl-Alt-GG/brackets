import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { FlattenedMatch, TournamentBundle } from '../types';
import * as OpenApi from '../../openapi';
import { toBracketViewerData } from '../bracket-adapter';
import { BracketViewer } from '../components/bracket-viewer';
import { MatchCard } from '../components/match-card';
import { MatchScoreEditor } from '../components/match-score-editor';
import { TeamLink } from '../components/team-link';
import { teamPath, useTournamentContext } from '../tournament-context';
import {
  cx,
  inputLabel,
  inputTeamId,
  involvesTeam,
  isBracket,
  isInProgress,
  isScored,
  isStageHappeningNow,
  matchStatus,
  matchWinner,
  nextMatch,
  pointsPhrase,
  sortTeamsByName,
  stageItemName,
  stageItemStandings,
  stageTypeName,
  type MatchOutcome,
} from '../utils';
import { Surface, SurfaceHeading } from '../ui';

function MyTeamPanel({
  matches,
  stageItemsById,
  teams,
}: {
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teams: OpenApi.FullTeamWithPlayers[];
}) {
  const { t } = useTranslation();
  const { myTeamId, publicPath, setMyTeamId } = useTournamentContext();
  const myTeam = teams.find((team) => team.id === myTeamId);

  if (teams.length === 0) return null;

  if (!myTeam) {
    return (
      <Surface>
        <SurfaceHeading title={t('overview.findYourTeam')} />
        <p className="text-sm text-base-content/80">{t('overview.pickYourTeam')}</p>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <select
            aria-label={t('common.yourTeam')}
            className="select w-full sm:w-80"
            onChange={(event) => setMyTeamId(Number(event.target.value))}
            value=""
          >
            <option disabled value="">
              {t('overview.chooseTeam')}
            </option>
            {sortTeamsByName(teams).map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </select>
          <Link className="link text-sm" to={`${publicPath}/teams`}>
            {t('overview.searchByPlayer')}
          </Link>
        </div>
      </Surface>
    );
  }

  const next = nextMatch(matches.filter(({ match }) => involvesTeam(match, myTeam.id)));
  const players = myTeam.players.map((player) => player.name).join(', ');

  return (
    <Surface className="border-accent/40">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-sm font-medium text-accent">{t('common.yourTeam')}</p>
          <h2 className="font-display text-2xl font-semibold">{myTeam.name}</h2>
          {players ? <p className="text-sm text-base-content/70">{players}</p> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className="btn btn-soft btn-sm" to={teamPath(publicPath, myTeam.id)}>
            {t('overview.allMatchesAndPlayers')}
          </Link>
          <button className="btn btn-ghost btn-sm" onClick={() => setMyTeamId(null)} type="button">
            {t('overview.changeTeam')}
          </button>
        </div>
      </div>
      {next ? (
        <div className="max-w-xl space-y-2">
          <p className="text-sm font-medium text-base-content/80">
            {isInProgress(matchStatus(next.match))
              ? t('overview.playingNowMine')
              : t('overview.nextMatch')}
          </p>
          <MatchCard entry={next} stageItemsById={stageItemsById} />
        </div>
      ) : (
        <p className="text-sm text-base-content/70">
          {t('overview.noUpcoming', { team: myTeam.name })}
        </p>
      )}
    </Surface>
  );
}

/** Where the table or bracket of a stage item is shown. */
export function stageItemPath(publicPath: string, stageItem: OpenApi.StageItemWithRounds) {
  return `${publicPath}/${isBracket(stageItem) ? 'bracket' : 'standings'}#stage-item-${stageItem.id}`;
}

export function OverviewSection({
  bundle,
  matches,
  stageItemsById,
  workspace = false,
}: {
  bundle: TournamentBundle;
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  /** The organizer's overview, where results are entered. Otherwise the Details page. */
  workspace?: boolean;
}) {
  const { t } = useTranslation();
  const { publicPath } = useTournamentContext();
  // A match that has started is in progress until its result is in, however long it runs over.
  const inProgress = matches.filter((entry) => isInProgress(matchStatus(entry.match)));
  // What is planned next, including matches that say who will play them ("Group A #1") before
  // the teams are known. A match with nothing to show yet, such as a final, is left out.
  const upcoming = matches
    .filter(({ match }) => {
      const status = matchStatus(match);
      return (
        status === 'scheduled' ||
        (status === 'waiting' &&
          (match.stage_item_input1 != null || match.stage_item_input2 != null))
      );
    })
    .slice(0, 6);
  const finished = matches.filter((entry) => matchStatus(entry.match) === 'finished').slice(-6);
  const editor = (entry: FlattenedMatch) =>
    workspace ? (
      <MatchScoreEditor
        entry={entry}
        stageItemsById={stageItemsById}
        tournamentId={bundle.tournament.id}
      />
    ) : undefined;

  return (
    <div className="space-y-6">
      {/* Organizers aren't looking for their own team. */}
      {workspace ? null : (
        <MyTeamPanel matches={matches} stageItemsById={stageItemsById} teams={bundle.teams} />
      )}

      <Surface>
        <SurfaceHeading
          title={
            inProgress.length === 0
              ? t('overview.comingUpNext')
              : workspace
                ? 'Waiting for results'
                : t('overview.playingNow')
          }
        />
        {workspace && inProgress.length > 0 ? (
          <p className="text-sm text-base-content/70">
            These matches have started. Enter each result as soon as the match is over: the
            standings, the bracket and the next matches follow from it.
          </p>
        ) : null}
        {inProgress.length === 0 && upcoming.length === 0 ? (
          <p className="text-sm text-base-content/70">{t('overview.nothingScheduled')}</p>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(inProgress.length > 0 ? inProgress : upcoming).map((entry) => (
            <MatchCard
              editor={inProgress.length > 0 ? editor(entry) : undefined}
              entry={entry}
              key={entry.match.id}
              stageItemsById={stageItemsById}
            />
          ))}
        </div>
        {inProgress.length > 0 && upcoming.length > 0 ? (
          <>
            <h3 className="pt-2 text-sm font-medium text-base-content/80">
              {t('overview.comingUpNext')}
            </h3>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {upcoming.map((entry) => (
                <MatchCard entry={entry} key={entry.match.id} stageItemsById={stageItemsById} />
              ))}
            </div>
          </>
        ) : null}
      </Surface>

      <div className="grid items-start gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <Surface>
          <SurfaceHeading title={t('overview.stagesAndGroups')} />
          {bundle.stages.length === 0 ? (
            <p className="text-sm text-base-content/70">{t('overview.notSetUp')}</p>
          ) : null}
          <div className="space-y-5">
            {bundle.stages.map((stage) => (
              <div className="space-y-3" key={stage.id}>
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className="text-lg font-semibold">{stage.name}</h3>
                  {isStageHappeningNow(stage, bundle.tournament) ? (
                    <span className="badge badge-soft badge-error badge-sm">
                      <span
                        aria-hidden="true"
                        className="status status-error motion-safe:animate-pulse"
                      />
                      {t('overview.happeningNow')}
                    </span>
                  ) : null}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {stage.stage_items.map((stageItem) => {
                    // Drafts are only shown in the stage editor, until they are published.
                    const stageItemMatches = stageItem.rounds
                      .filter((round) => !round.is_draft)
                      .flatMap((round) => round.matches);
                    const played = stageItemMatches.filter(isScored).length;

                    return (
                      <Link
                        className="card border border-base-300 bg-base-100/50 p-4 transition hover:border-primary/50 hover:bg-base-100/80"
                        key={stageItem.id}
                        to={stageItemPath(publicPath, stageItem)}
                      >
                        <p className="text-xs text-base-content/70">
                          {stageTypeName(stageItem, t)}
                        </p>
                        <h4 className="mt-2 font-semibold">{stageItemName(stageItem, t)}</h4>
                        <p className="mt-2 text-sm text-base-content/70">
                          {t('common.teamCount', { count: stageItem.team_count })} ·{' '}
                          {t('common.matchesPlayed', {
                            played,
                            total: stageItemMatches.length,
                          })}
                        </p>
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </Surface>

        <Surface>
          <SurfaceHeading title={t('overview.latestResults')} />
          {finished.length === 0 ? (
            <p className="text-sm text-base-content/70">{t('overview.noResults')}</p>
          ) : (
            <div className="space-y-3">
              {finished.toReversed().map((entry) => (
                <MatchCard entry={entry} key={entry.match.id} stageItemsById={stageItemsById} />
              ))}
            </div>
          )}
        </Surface>
      </div>
    </div>
  );
}

/** Same emphasis as the match cards: the winner stands out, the loser recedes. */
function sideClass(winner: MatchOutcome, side: 1 | 2) {
  if (winner === side) return 'font-semibold text-base-content';
  if (winner === 1 || winner === 2) return 'text-base-content/60';
  return 'text-base-content/90';
}

export function StageItemVisualization({
  showMatches = true,
  stageItem,
  stageItemsById,
  standings,
  teamMap,
  tournamentId,
}: {
  showMatches?: boolean;
  stageItem: OpenApi.StageItemWithRounds;
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  standings: TournamentBundle['standings'];
  teamMap: Map<number, OpenApi.FullTeamWithPlayers>;
  tournamentId: number;
}) {
  const { t } = useTranslation();
  const entries = stageItemStandings(stageItem, standings);
  const bracketData = isBracket(stageItem)
    ? toBracketViewerData(stageItem, stageItemsById, tournamentId, t)
    : null;
  // Drafts are only shown in the stage editor, until they are published.
  const publishedRounds = stageItem.rounds.filter((round) => !round.is_draft);

  return (
    <div className="card border border-base-300 bg-base-100/50 p-4">
      <h4 className="text-lg font-semibold">{stageItemName(stageItem, t)}</h4>
      <p className="mt-1 text-sm text-base-content/70">
        {stageTypeName(stageItem, t)} · {t('common.teamCount', { count: stageItem.team_count })}
      </p>

      {isBracket(stageItem) ? (
        <div className="mt-4">
          {bracketData ? (
            <BracketViewer data={bracketData} />
          ) : (
            <p className="text-sm text-base-content/70">{t('overview.bracketPending')}</p>
          )}
        </div>
      ) : (
        <div className={cx('mt-4 grid gap-4', showMatches && 'lg:grid-cols-[0.9fr_1.1fr]')}>
          <div className="space-y-3">
            <p className="text-sm font-medium text-base-content/80">{t('overview.table')}</p>
            <div className="space-y-2">
              {entries.length === 0 ? (
                <p className="text-sm text-base-content/70">{t('overview.noTeams')}</p>
              ) : null}
              {entries.map(({ input, standing }, index) => {
                const team = teamMap.get(input.team_id);
                return (
                  <div
                    className="flex items-center justify-between gap-3 rounded-field border border-base-300 bg-base-200/60 px-3 py-2 text-sm"
                    key={input.id}
                  >
                    <span className="flex items-center gap-3">
                      <span className="w-5 text-base-content/70">{index + 1}</span>
                      <TeamLink className="font-medium" teamId={input.team_id}>
                        {team?.name ?? inputLabel(input, stageItemsById, t)}
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
                  </div>
                );
              })}
            </div>
          </div>
          {showMatches ? (
            <div className="space-y-3">
              <p className="text-sm font-medium text-base-content/80">{t('overview.matches')}</p>
              {/* Equal team columns keep "vs" in the middle of every row, and sharing one grid
                  between all rounds keeps it in a straight line even next to wider scores. */}
              <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-3">
                {publishedRounds.map((round) => (
                  <div
                    className="col-span-3 grid grid-cols-subgrid gap-y-2 rounded-box border border-base-300 bg-base-200/60 p-3"
                    key={round.id}
                  >
                    <p className="col-span-3 text-sm font-semibold">{round.name}</p>
                    {round.matches.map((match) => {
                      const winner = matchWinner(match);
                      return (
                        <div
                          className="col-span-3 grid grid-cols-subgrid items-center rounded-field bg-base-100/60 px-3 py-2 text-sm"
                          key={match.id}
                        >
                          <TeamLink
                            className={cx('break-words text-right', sideClass(winner, 1))}
                            teamId={inputTeamId(match.stage_item_input1)}
                          >
                            {inputLabel(match.stage_item_input1, stageItemsById, t)}
                          </TeamLink>
                          <span className="text-center font-semibold tabular-nums">
                            {isScored(match)
                              ? `${match.stage_item_input1_score} – ${match.stage_item_input2_score}`
                              : t('common.vs')}
                          </span>
                          <TeamLink
                            className={cx('break-words', sideClass(winner, 2))}
                            teamId={inputTeamId(match.stage_item_input2)}
                          >
                            {inputLabel(match.stage_item_input2, stageItemsById, t)}
                          </TeamLink>
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
