import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { FlattenedMatch, TournamentBundle } from '../types';
import * as OpenApi from '../../openapi';
import { MatchCard } from '../components/match-card';
import { MatchScoreEditor } from '../components/match-score-editor';
import { teamPath, useTournamentContext } from '../tournament-context';
import {
  involvesTeam,
  isBracket,
  isScored,
  stageItemName,
  stageName,
  stageTypeName,
} from '../matches';
import { isInProgress, isStageHappeningNow, matchStatus, nextMatch } from '../tournament-rules';
import { cx, sortTeamsByName } from '../utils';
import { Surface, SurfaceHeading } from '../ui';

function MyTeamPanel({
  matches,
  stageItemsById,
  teams,
  workspace,
}: {
  matches: FlattenedMatch[];
  stageItemsById: Map<number, OpenApi.StageItemWithRounds>;
  teams: OpenApi.TournamentTeamWithPlayers[];
  /**
   * The organizer's overview. It keeps showing the team picked on the public view, for organizers
   * who play, but doesn't ask the others to pick one: picking and changing stay on the public view.
   */
  workspace: boolean;
}) {
  const { t } = useTranslation();
  const { myTeamId, publicPath, setMyTeamId } = useTournamentContext();
  const myTeam = teams.find((team) => team.id === myTeamId);

  if (teams.length === 0) return null;

  if (!myTeam) {
    if (workspace) return null;
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
          {workspace ? null : (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setMyTeamId(null)}
              type="button"
            >
              {t('overview.changeTeam')}
            </button>
          )}
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

/**
 * The steps from a new tournament to one that can be played, for its organizers, each with a link
 * to the page where it is done.
 */
function SetupChecklist({
  hasTeams,
  stagesHaveTeams,
  tournamentId,
}: {
  hasTeams: boolean;
  stagesHaveTeams: boolean;
  tournamentId: number;
}) {
  const { t } = useTranslation();
  const base = `/tournaments/${tournamentId}`;
  const steps = [
    {
      done: hasTeams,
      label: t('workspace.teams'),
      text: t('workspace.setupTeams'),
      to: `${base}/teams`,
    },
    {
      done: stagesHaveTeams,
      label: t('workspace.stages'),
      text: t('workspace.setupStages'),
      to: `${base}/stages`,
    },
    // Nothing tells whether it was shared, so it stays a reminder.
    {
      done: false,
      label: t('workspace.settings'),
      text: t('workspace.setupShare'),
      to: `${base}/settings`,
    },
  ];

  return (
    <Surface>
      <SurfaceHeading title={t('workspace.setupTitle')} />
      <ol className="steps steps-vertical">
        {steps.map((step) => (
          <li
            className={cx('step', step.done && 'step-primary')}
            data-content={step.done ? '✓' : undefined}
            key={step.to}
          >
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-start">
              <span className={cx(step.done && 'text-base-content/70')}>{step.text}</span>
              {step.done ? (
                <span className="sr-only">{t('workspace.setupDone')}</span>
              ) : (
                <Link className="btn btn-soft btn-sm" to={step.to}>
                  {step.label}
                </Link>
              )}
            </span>
          </li>
        ))}
      </ol>
    </Surface>
  );
}

/** Where the table or bracket of a stage item is shown. */
export function stageItemPath(publicPath: string, stageItem: OpenApi.StageItemWithRounds) {
  return `${publicPath}/${isBracket(stageItem) ? 'bracket' : 'standings'}#stage-item-${stageItem.id}`;
}

/** Where organizers find a stage item: a group in the standings, a bracket in the stage editor. */
function workspaceStageItemPath(tournamentId: number, stageItem: OpenApi.StageItemWithRounds) {
  const page = isBracket(stageItem) ? 'stages' : 'rankings';
  return `/tournaments/${tournamentId}/${page}#stage-item-${stageItem.id}`;
}

/** The results the overview shows. The schedule has all of them. */
const LATEST_RESULTS = 4;

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
  const tournamentId = bundle.tournament.id;
  const schedulePath = workspace
    ? `/tournaments/${tournamentId}/schedule`
    : `${publicPath}/schedule`;
  // A match that has started is in progress until its result is in, however long it runs over.
  const inProgress = matches.filter((entry) => isInProgress(matchStatus(entry.match)));
  // What is planned, including matches that say who will play them ("Group A #1") before the
  // teams are known. A match with nothing to show yet, such as a final, is left out.
  const planned = matches.filter(({ match }) => {
    const status = matchStatus(match);
    return (
      status === 'scheduled' ||
      (status === 'waiting' && (match.stage_item_input1 != null || match.stage_item_input2 != null))
    );
  });
  // The matches that start next. The rounds after them are on the schedule.
  const upcoming = planned.filter(({ match }) => match.start_time === planned[0]?.match.start_time);
  const allFinished = matches.filter((entry) => matchStatus(entry.match) === 'finished');
  const finished = allFinished.slice(-LATEST_RESULTS);
  const hasTeams = bundle.teams.length > 0;
  const stagesHaveTeams = bundle.stages.some((stage) =>
    stage.stage_items.some((stageItem) => stageItem.inputs.some((input) => input.team_id != null)),
  );
  const scheduleLink = (label: string) => (
    <Link className="btn btn-ghost btn-sm" to={schedulePath}>
      {label}
    </Link>
  );
  const editor = (entry: FlattenedMatch) =>
    workspace ? (
      <MatchScoreEditor entry={entry} stageItemsById={stageItemsById} tournamentId={tournamentId} />
    ) : undefined;

  // Until teams play in its stages, organizers see what is left to set up, and nothing else.
  if (workspace && !(hasTeams && stagesHaveTeams)) {
    return (
      <SetupChecklist
        hasTeams={hasTeams}
        stagesHaveTeams={stagesHaveTeams}
        tournamentId={tournamentId}
      />
    );
  }

  return (
    <div className="space-y-6">
      <MyTeamPanel
        matches={matches}
        stageItemsById={stageItemsById}
        teams={bundle.teams}
        workspace={workspace}
      />

      <Surface>
        <SurfaceHeading
          actions={matches.length > 0 ? scheduleLink(t('overview.fullSchedule')) : null}
          title={
            inProgress.length === 0
              ? t('overview.comingUpNext')
              : workspace
                ? t('workspace.waitingForResults')
                : t('overview.playingNow')
          }
        />
        {workspace && inProgress.length > 0 ? (
          <p className="text-sm text-base-content/70">{t('workspace.enterResults')}</p>
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
                  <h3 className="text-lg font-semibold">{stageName(stage, t)}</h3>
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
                        to={
                          workspace
                            ? workspaceStageItemPath(tournamentId, stageItem)
                            : stageItemPath(publicPath, stageItem)
                        }
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
          <SurfaceHeading
            actions={
              allFinished.length > finished.length ? scheduleLink(t('overview.allResults')) : null
            }
            title={t('overview.latestResults')}
          />
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
