import { useMemo, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, Navigate, NavLink, useParams } from 'react-router';

import * as OpenApi from '../../openapi';
import { fetchTournamentBundle, TOURNAMENT_BUNDLE_QUERY_KEY } from '../api';
import { TournamentStatusBadge } from '../components/tournament-status-badge';
import { useMyTeam, useSession } from '../hooks';
import { TournamentContext } from '../tournament-context';
import type { TournamentBundle, TournamentSection } from '../types';
import {
  compareMatchesByTime,
  cx,
  flattenMatches,
  getErrorMessage,
  isBracket,
  isScored,
  publicTournamentPath,
  tournamentDateLabel,
} from '../utils';
import { EmptyState, ErrorState, LoadingState, PageShell } from '../ui';
import { OverviewSection } from '../sections/tournament-overview';
import { BracketSection } from '../sections/tournament-bracket';
import { PlayersSection, TeamsSection } from '../sections/tournament-roster';
import { TeamDetailSection, TeamDirectorySection } from '../sections/tournament-teams';
import {
  BigScreenSchedule,
  RankingsSection,
  ScheduleSection,
  SettingsSection,
  StandingsSection,
  StagesSection,
} from '../sections/tournament-management';

const MANAGEMENT_SECTIONS: ReadonlySet<TournamentSection> = new Set([
  'players',
  'rankings',
  'settings',
  'stages',
  'teams',
]);

/** The Details page that shows a workspace page's information, for people who can't manage. */
const DETAILS_SUFFIXES: Partial<Record<TournamentSection, string>> = {
  overview: '',
  schedule: '/schedule',
};

const SECTION_TITLES: Partial<Record<TournamentSection, string>> = {
  'dashboard-bracket': 'Bracket',
  'dashboard-present-schedule': 'Now and next',
  'dashboard-present-standings': 'Standings',
  'dashboard-schedule': 'Schedule',
  'dashboard-standings': 'Standings',
  'dashboard-teams': 'Teams',
  players: 'Players',
  rankings: 'Rankings',
  schedule: 'Schedule',
  settings: 'Settings',
  stages: 'Stages',
  teams: 'Teams',
};

type Tab = { end?: boolean; label: string; to: string };

function detailsTabs(publicPath: string, stages: OpenApi.StageWithStageItems[]): Tab[] {
  const stageItems = stages.flatMap((stage) => stage.stage_items);
  return [
    { end: true, label: 'Overview', to: publicPath },
    { label: 'Schedule', to: `${publicPath}/schedule` },
    ...(stageItems.some((stageItem) => !isBracket(stageItem))
      ? [{ label: 'Standings', to: `${publicPath}/standings` }]
      : []),
    ...(stageItems.some(isBracket) ? [{ label: 'Bracket', to: `${publicPath}/bracket` }] : []),
    { label: 'Teams', to: `${publicPath}/teams` },
  ];
}

function workspaceTabs(tournamentId: number): Tab[] {
  const base = `/tournaments/${tournamentId}`;
  return [
    { end: true, label: 'Overview', to: base },
    { label: 'Players', to: `${base}/players` },
    { label: 'Teams', to: `${base}/teams` },
    { label: 'Stages', to: `${base}/stages` },
    { label: 'Schedule', to: `${base}/schedule` },
    { label: 'Rankings', to: `${base}/rankings` },
    { label: 'Settings', to: `${base}/settings` },
  ];
}

function TournamentHeader({
  actions,
  matchCount,
  matchesPlayed,
  tabs,
  teamCount,
  tournament,
}: {
  actions: ReactNode;
  matchCount: number;
  matchesPlayed: number;
  tabs: Tab[];
  teamCount: number;
  tournament: OpenApi.Tournament;
}) {
  return (
    <header className="card border border-base-300 bg-base-200/60 backdrop-blur">
      <div className="card-body gap-5 pb-0">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="space-y-3">
            <h1 className="font-display text-3xl font-semibold tracking-tight md:text-4xl">
              {tournament.name}
            </h1>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-base-content/70">
              <TournamentStatusBadge tournament={tournament} />
              <span>{tournamentDateLabel(tournament)}</span>
              {/* The line wraps on phones, where a separator would dangle at a line end. */}
              <span aria-hidden="true" className="hidden sm:inline">
                ·
              </span>
              <span>{teamCount === 1 ? '1 team' : `${teamCount} teams`}</span>
              {matchCount > 0 ? (
                <>
                  <span aria-hidden="true" className="hidden sm:inline">
                    ·
                  </span>
                  <span>
                    {matchesPlayed} of {matchCount} matches played
                  </span>
                </>
              ) : null}
            </p>
          </div>
          {actions}
        </div>
        <nav
          aria-label="Tournament pages"
          className="tabs tabs-border flex-nowrap overflow-x-auto [scrollbar-width:none]"
        >
          {tabs.map((tab) => (
            <NavLink
              className={({ isActive }) => cx('tab shrink-0', isActive && 'tab-active')}
              end={tab.end}
              key={tab.to}
              to={tab.to}
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}

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
  const hasBrackets = stageItems.some(isBracket);
  const team = teamMap.get(teamId ?? -1);
  const pageTitle = section === 'dashboard-team' ? team?.name : SECTION_TITLES[section];
  const context = {
    isBigScreen,
    // A remembered team can have been deleted since, and a screen at the venue is for everyone.
    myTeamId: !isBigScreen && teamMap.has(myTeamId ?? -1) ? myTeamId : null,
    publicPath,
    setMyTeamId,
  };

  let content: ReactNode;
  switch (section) {
    case 'overview':
    case 'dashboard':
      content = (
        <OverviewSection bundle={bundle} matches={matches} stageItemsById={stageItemsById} />
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
        <EmptyState
          text="The bracket appears here once the organizers have set up the tournament."
          title="No bracket yet"
        />
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
              Exit big screen
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
                    Manage
                  </Link>
                ) : null
              ) : (
                <Link className="btn btn-ghost btn-sm" to={publicPath}>
                  Details
                </Link>
              )
            }
            matchCount={matches.length}
            matchesPlayed={matches.filter((entry) => isScored(entry.match)).length}
            tabs={
              dashboardMode ? detailsTabs(publicPath, bundle.stages) : workspaceTabs(tournament.id)
            }
            teamCount={bundle.teams.length}
            tournament={tournament}
          />
          {content}
        </section>
      )}
    </TournamentContext.Provider>
  );
}

export function TournamentPage({ section }: { section: TournamentSection }) {
  const params = useParams();
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
  const workspace = useQuery({
    enabled: Boolean(tournamentKey) && !isLockedOut && !sendVisitorToDetails,
    queryFn: () => fetchTournamentBundle(tournamentKey, dashboardMode, isAuthenticated),
    queryKey: [...TOURNAMENT_BUNDLE_QUERY_KEY, tournamentKey, dashboardMode, session?.access_token],
    // The Details pages follow a live event, and the big screens run unattended.
    refetchInterval: dashboardMode ? 30_000 : false,
  });

  if (sendVisitorToDetails) {
    return <Navigate replace to={`/tournaments/${tournamentKey}/dashboard${detailsSuffix}`} />;
  }

  if (isLockedOut) {
    return (
      <ErrorState
        action={
          <Link className="btn btn-primary btn-sm" to="/login">
            Organizer login
          </Link>
        }
        error="This area is only available to organizers."
        title="Organizers only"
      />
    );
  }

  if (workspace.isPending) {
    return <LoadingState title="Loading tournament…" />;
  }

  if (!workspace.data) {
    return (
      <ErrorState
        action={
          <button className="btn btn-sm" onClick={() => void workspace.refetch()} type="button">
            Retry
          </button>
        }
        error={getErrorMessage(workspace.error)}
        title="Unable to load tournament"
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
            Open the Details page
          </Link>
        }
        error="You can follow this tournament, but you can't manage it."
        title="Read-only access"
      />
    );
  }

  return (
    <TournamentView
      bundle={workspace.data}
      section={section}
      stageItemId={params.stageItemId ? Number(params.stageItemId) : null}
      teamId={params.teamId ? Number(params.teamId) : null}
      tournamentKey={tournamentKey}
    />
  );
}

export function NotFoundPage() {
  return (
    <PageShell title="Page not found">
      <EmptyState
        action={
          <Link className="btn btn-primary btn-sm" to="/">
            Back to the tournaments
          </Link>
        }
        text="The link may be mistyped, or the page has moved."
        title="There's nothing here"
      />
    </PageShell>
  );
}
