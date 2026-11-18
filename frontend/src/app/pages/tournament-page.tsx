import { lazy, Suspense, useMemo, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { I18nextProvider, useTranslation } from 'react-i18next';
import { Link, Navigate, useLocation, useParams } from 'react-router';

import { fetchTournamentBundle, TOURNAMENT_BUNDLE_QUERY_KEY } from '../api';
import { useMyTeam, useSession } from '../hooks';
import { englishI18n } from '../locales';
import { TournamentContext } from '../tournament-context';
import type { TournamentBundle, TournamentSection } from '../types';
import { getErrorMessage } from '../errors';
import {
  compareMatchesByTime,
  flattenMatches,
  hasBracketView,
  isBracket,
  isScored,
} from '../matches';
import { loginPath, publicTournamentPath } from '../urls';
import { EmptyState, ErrorState, LoadingState, PageShell } from '../ui';
import { detailsTabs, TournamentHeader, workspaceTabs } from '../sections/tournament-header';
import { OverviewSection } from '../sections/tournament-overview';
import { BracketSection } from '../sections/tournament-bracket';
import { BigScreenSchedule, ScheduleSection } from '../sections/tournament-schedule';
import { StandingsSection } from '../sections/tournament-standings';
import { TeamDetailSection, TeamDirectorySection } from '../sections/tournament-teams';

// Only organizers open the workspace, so visitors never download its forms.
const PlayersSection = lazy(() =>
  import('../sections/tournament-roster').then((module) => ({ default: module.PlayersSection })),
);
const TeamsSection = lazy(() =>
  import('../sections/tournament-roster').then((module) => ({ default: module.TeamsSection })),
);
const RankingsSection = lazy(() =>
  import('../sections/tournament-rankings').then((module) => ({
    default: module.RankingsSection,
  })),
);
const SettingsSection = lazy(() =>
  import('../sections/tournament-settings').then((module) => ({
    default: module.SettingsSection,
  })),
);
const StagesSection = lazy(() =>
  import('../sections/tournament-stages').then((module) => ({
    default: module.StagesSection,
  })),
);

const MANAGEMENT_SECTIONS: ReadonlySet<TournamentSection> = new Set([
  'players',
  'rankings',
  'settings',
  'stages',
  'teams',
]);

/**
 * The Details page that shows a workspace page's information, for people who can't manage. The
 * standings send a tournament without groups on to its bracket.
 */
const DETAILS_SUFFIXES: Partial<Record<TournamentSection, string>> = {
  overview: '',
  schedule: '/schedule',
  stages: '/standings',
  teams: '/teams',
};

const DETAILS_TITLES = {
  'dashboard-bracket': 'tournament.bracket',
  'dashboard-present-schedule': 'tournament.nowAndNext',
  'dashboard-present-standings': 'tournament.standings',
  'dashboard-schedule': 'tournament.schedule',
  'dashboard-standings': 'tournament.standings',
  'dashboard-teams': 'tournament.teams',
} as const satisfies Partial<Record<TournamentSection, string>>;

// The workspace is English only.
const WORKSPACE_TITLES: Partial<Record<TournamentSection, string>> = {
  players: 'Players',
  rankings: 'Rankings',
  schedule: 'Schedule',
  settings: 'Settings',
  stages: 'Stages',
  teams: 'Teams',
};

/** The page itself, once the tournament has loaded. */
function TournamentView({
  bundle,
  section,
  stageItemId,
  teamId,
  tournamentKey,
}: {
  bundle: TournamentBundle;
  section: TournamentSection;
  stageItemId: number | null;
  teamId: number | null;
  tournamentKey: string;
}) {
  const { t } = useTranslation();
  const { canManage, tournament } = bundle;
  const dashboardMode = section.startsWith('dashboard');
  const isBigScreen = section.startsWith('dashboard-present');
  const [myTeamId, setMyTeamId] = useMyTeam(tournament.id);

  const teamMap = useMemo(
    () => new Map(bundle.teams.map((team) => [team.id, team] as const)),
    [bundle.teams],
  );
  const stageItemsById = useMemo(
    () =>
      new Map(
        bundle.stages.flatMap((stage) =>
          stage.stage_items.map((stageItem) => [stageItem.id, stageItem] as const),
        ),
      ),
    [bundle.stages],
  );
  // Draft rounds are only shown in the stage editor, until they are published.
  const matches = useMemo(
    () =>
      flattenMatches(bundle.stages)
        .filter(({ round }) => !round.is_draft)
        .toSorted(compareMatchesByTime),
    [bundle.stages],
  );

  const publicPath = dashboardMode
    ? `/tournaments/${tournamentKey}/dashboard`
    : publicTournamentPath(tournament);
  const stageItems = bundle.stages.flatMap((stage) => stage.stage_items);
  const hasGroups = stageItems.some((stageItem) => !isBracket(stageItem));
  const hasBrackets = stageItems.some(hasBracketView);
  const team = teamMap.get(teamId ?? -1);
  const detailsTitle = DETAILS_TITLES[section as keyof typeof DETAILS_TITLES];
  const pageTitle =
    section === 'dashboard-team'
      ? team?.name
      : detailsTitle
        ? t(detailsTitle)
        : WORKSPACE_TITLES[section];
  // A remembered team can have been deleted since, and a screen at the venue is for everyone.
  const shownTeamId = !isBigScreen && teamMap.has(myTeamId ?? -1) ? myTeamId : null;
  // The same object until something in it changes, so a refresh of the tournament doesn't make
  // everything that reads it render again.
  const context = useMemo(
    () => ({ isBigScreen, myTeamId: shownTeamId, publicPath, setMyTeamId }),
    [isBigScreen, publicPath, setMyTeamId, shownTeamId],
  );

  let content: ReactNode;
  switch (section) {
    case 'overview':
    case 'dashboard':
      content = (
        <OverviewSection
          bundle={bundle}
          matches={matches}
          stageItemsById={stageItemsById}
          workspace={!dashboardMode}
        />
      );
      break;
    case 'schedule':
    case 'dashboard-schedule':
      content = (
        <ScheduleSection
          bigScreenPath={`${publicPath}/present/schedule`}
          canManage={!dashboardMode}
          matches={matches}
          stageItemsById={stageItemsById}
          tournamentId={tournament.id}
        />
      );
      break;
    case 'dashboard-standings':
      content =
        !hasGroups && hasBrackets ? (
          <Navigate replace to={`${publicPath}/bracket`} />
        ) : (
          <StandingsSection
            bigScreenPath={`${publicPath}/present/standings`}
            rankings={bundle.rankings}
            stages={bundle.stages}
            standings={bundle.standings}
            teamMap={teamMap}
          />
        );
      break;
    case 'dashboard-bracket':
      content = hasBrackets ? (
        <BracketSection
          bigScreenPath={`${publicPath}/present/standings`}
          stages={bundle.stages}
          stageItemsById={stageItemsById}
          tournamentId={tournament.id}
        />
      ) : hasGroups ? (
        <Navigate replace to={`${publicPath}/standings`} />
      ) : (
        <EmptyState text={t('tournament.noBracketText')} title={t('tournament.noBracketTitle')} />
      );
      break;
    case 'dashboard-teams':
      content = <TeamDirectorySection teams={bundle.teams} />;
      break;
    case 'dashboard-team':
      content = (
        <TeamDetailSection
          bundle={bundle}
          matches={matches}
          stageItemsById={stageItemsById}
          teamId={teamId}
        />
      );
      break;
    case 'dashboard-present-schedule':
      content = <BigScreenSchedule matches={matches} stageItemsById={stageItemsById} />;
      break;
    case 'dashboard-present-standings':
      content = (
        <>
          {hasGroups || !hasBrackets ? (
            <StandingsSection
              compact
              rankings={bundle.rankings}
              stages={bundle.stages}
              standings={bundle.standings}
              teamMap={teamMap}
            />
          ) : null}
          <BracketSection
            stages={bundle.stages}
            stageItemsById={stageItemsById}
            tournamentId={tournament.id}
          />
        </>
      );
      break;
    case 'players':
      content = <PlayersSection bundle={bundle} />;
      break;
    case 'teams':
      content = <TeamsSection bundle={bundle} />;
      break;
    case 'rankings':
      content = <RankingsSection bundle={bundle} teamMap={teamMap} />;
      break;
    case 'settings':
      content = <SettingsSection bundle={bundle} />;
      break;
    case 'stages':
      content = (
        <StagesSection
          bundle={bundle}
          focusStageItem={stageItemId ? (stageItemsById.get(stageItemId) ?? null) : null}
        />
      );
      break;
  }

  return (
    <TournamentContext.Provider value={context}>
      <title>
        {[pageTitle, tournament.name, 'Ctrl-Alt-GG Bracket'].filter(Boolean).join(' · ')}
      </title>
      {isBigScreen ? (
        <section className="space-y-6">
          <header className="flex flex-wrap items-center justify-between gap-4">
            <h1 className="font-display text-4xl font-semibold tracking-tight md:text-5xl">
              {tournament.name}
            </h1>
            <Link
              className="link link-hover text-sm text-base-content/70"
              to={section === 'dashboard-present-schedule' ? `${publicPath}/schedule` : publicPath}
            >
              {t('tournament.exitBigScreen')}
            </Link>
          </header>
          {content}
        </section>
      ) : (
        <section className="space-y-6">
          <TournamentHeader
            actions={
              dashboardMode ? (
                canManage ? (
                  <Link className="btn btn-ghost btn-sm" to={`/tournaments/${tournament.id}`}>
                    {t('common.manage')}
                  </Link>
                ) : null
              ) : (
                <Link className="btn btn-ghost btn-sm" to={publicPath}>
                  {t('common.details')}
                </Link>
              )
            }
            matchCount={matches.length}
            matchesPlayed={matches.filter((entry) => isScored(entry.match)).length}
            tabs={
              dashboardMode
                ? detailsTabs(publicPath, bundle.stages, t)
                : workspaceTabs(tournament.id)
            }
            teamCount={bundle.teams.length}
            tournament={tournament}
          />
          <Suspense fallback={<LoadingState title={t('common.loading')} />}>{content}</Suspense>
        </section>
      )}
    </TournamentContext.Provider>
  );
}

export function TournamentPage({ section }: { section: TournamentSection }) {
  const page = <TournamentPageContent section={section} />;
  // The workspace is English only, like everything organizers use.
  return section.startsWith('dashboard') ? (
    page
  ) : (
    <I18nextProvider i18n={englishI18n}>
      <div className="contents" lang="en">
        {page}
      </div>
    </I18nextProvider>
  );
}

function TournamentPageContent({ section }: { section: TournamentSection }) {
  const { t } = useTranslation();
  const params = useParams();
  const { pathname } = useLocation();
  const [session] = useSession();
  const tournamentKey = params.tournamentKey ?? '';
  const dashboardMode = section.startsWith('dashboard');
  const isAuthenticated = Boolean(session);
  const isManagementSection = MANAGEMENT_SECTIONS.has(section);
  const isLockedOut = isManagementSection && !isAuthenticated;
  // Visitors can't manage anything, so the workspace sends them to the Details pages.
  const detailsSuffix = DETAILS_SUFFIXES[section];
  const sendVisitorToDetails = !dashboardMode && !isAuthenticated && detailsSuffix != null;

  // Refetching keeps showing the current data, so open panels and forms survive every save.
  // Leaving the page, or a newer load of it, cancels the requests of the one before.
  const workspace = useQuery({
    enabled: Boolean(tournamentKey) && !isLockedOut && !sendVisitorToDetails,
    queryFn: ({ signal }) =>
      fetchTournamentBundle(tournamentKey, dashboardMode, isAuthenticated, signal),
    queryKey: [...TOURNAMENT_BUNDLE_QUERY_KEY, tournamentKey, dashboardMode, session?.user_id],
    // The Details pages follow a live event, and the big screens run unattended. Organizers
    // work side by side during an event, so the workspace also picks up what the others changed,
    // less often. A form that is being filled in keeps what was typed into it (`useSavedForm`).
    refetchInterval: dashboardMode ? 30_000 : 60_000,
  });

  if (sendVisitorToDetails) {
    return <Navigate replace to={`/tournaments/${tournamentKey}/dashboard${detailsSuffix}`} />;
  }

  if (isLockedOut) {
    return (
      <ErrorState
        action={
          <Link className="btn btn-primary btn-sm" to={loginPath(pathname)}>
            {t('nav.organizerLogin')}
          </Link>
        }
        error={t('tournament.organizersOnlyText')}
        title={t('tournament.organizersOnlyTitle')}
      />
    );
  }

  if (workspace.isPending) {
    return <LoadingState title={t('tournament.loading')} />;
  }

  if (!workspace.data) {
    return (
      <ErrorState
        action={
          <button className="btn btn-sm" onClick={() => void workspace.refetch()} type="button">
            {t('common.retry')}
          </button>
        }
        error={getErrorMessage(workspace.error)}
        title={t('tournament.loadFailed')}
      />
    );
  }

  const { canManage, tournament } = workspace.data;

  if (!dashboardMode && !canManage && detailsSuffix != null) {
    return <Navigate replace to={`/tournaments/${tournamentKey}/dashboard${detailsSuffix}`} />;
  }

  if (isManagementSection && !canManage) {
    return (
      <ErrorState
        action={
          <Link className="btn btn-primary btn-sm" to={publicTournamentPath(tournament)}>
            {t('tournament.openDetails')}
          </Link>
        }
        error={t('tournament.readOnlyText')}
        title={t('tournament.readOnlyTitle')}
      />
    );
  }

  return (
    <>
      {workspace.isRefetchError || workspace.fetchStatus === 'paused' ? (
        <div className="alert alert-warning alert-soft flex-wrap" role="alert">
          <div>
            <p className="font-semibold">{t('tournament.stale')}</p>
            <p className="text-sm">
              {t('tournament.lastUpdated', {
                time: new Date(workspace.dataUpdatedAt).toLocaleString(),
              })}
            </p>
          </div>
          <button
            className="btn btn-sm"
            disabled={workspace.isFetching}
            onClick={() => void workspace.refetch()}
            type="button"
          >
            {workspace.isFetching ? t('tournament.retrying') : t('tournament.retryUpdates')}
          </button>
        </div>
      ) : null}
      <TournamentView
        bundle={workspace.data}
        section={section}
        stageItemId={params.stageItemId ? Number(params.stageItemId) : null}
        teamId={params.teamId ? Number(params.teamId) : null}
        tournamentKey={tournamentKey}
      />
    </>
  );
}

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <PageShell title={t('errors.pageNotFound')}>
      <EmptyState
        action={
          <Link className="btn btn-primary btn-sm" to="/">
            {t('errors.backToTournaments')}
          </Link>
        }
        text={t('errors.nothingHereText')}
        title={t('errors.nothingHereTitle')}
      />
    </PageShell>
  );
}
