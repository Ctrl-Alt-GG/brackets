import { useMemo } from 'react';
import { Link, NavLink, useParams } from 'react-router';

import * as OpenApi from '../../openapi';
import { fetchTournamentBundle } from '../api';
import { useResource } from '../hooks';
import type { FlashMessage, Session, TournamentSection } from '../types';
import { compareMatchesByTime, cx, flattenMatches, isScored } from '../utils';
import { Button, ErrorState, LoadingState, PageShell, Surface } from '../ui';
import { OverviewSection } from '../sections/tournament-overview';
import { BracketSection } from '../sections/tournament-bracket';
import { PlayersSection, TeamsSection } from '../sections/tournament-roster';
import {
  RankingsSection,
  ResultsSection,
  ScheduleSection,
  SettingsSection,
  StandingsSection,
  StagesSection,
} from '../sections/tournament-management';

function TournamentNav({
  dashboardMode,
  canManage,
  tournamentKey,
}: {
  dashboardMode: boolean;
  canManage: boolean;
  tournamentKey: string;
}) {
  const items = dashboardMode
    ? [
        ['dashboard', 'Overview'],
        ['dashboard/bracket', 'Bracket'],
        ['dashboard/standings', 'Standings'],
        ['dashboard/present/courts', 'Courts'],
      ]
    : [
        ['', 'Overview'],
        ...(canManage
          ? ([
              ['players', 'Players'],
              ['teams', 'Teams'],
            ] as const)
          : []),
        ['schedule', 'Schedule'],
        ...(canManage
          ? ([
              ['rankings', 'Rankings'],
              ['stages', 'Stages'],
            ] as const)
          : []),
        ['results', 'Results'],
        ...(canManage ? ([['settings', 'Settings']] as const) : []),
      ];

  return (
    <div className="flex flex-wrap items-center gap-2">
      {items.map(([suffix, label]) => {
        const target = suffix
          ? `/tournaments/${tournamentKey}/${suffix}`
          : `/tournaments/${tournamentKey}`;
        return (
          <NavLink
            className={({ isActive }) =>
              cx(
                'rounded-full px-4 py-2 text-sm font-semibold transition',
                isActive
                  ? 'bg-brand-600 text-white'
                  : 'bg-white/10 text-zinc-200 hover:bg-white/20',
              )
            }
            key={label}
            end
            to={target}
          >
            {label}
          </NavLink>
        );
      })}
      {dashboardMode ? (
        <NavLink
          className="px-3 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500 transition hover:text-zinc-300"
          to={`/tournaments/${tournamentKey}/dashboard/present/standings`}
        >
          Big screen
        </NavLink>
      ) : null}
    </div>
  );
}

const TOURNAMENT_STATUS_LABELS: Record<OpenApi.TournamentStatus, string> = {
  ARCHIVED: 'Finished',
  OPEN: 'Running',
};

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.25rem] border border-white/10 bg-black/20 p-4">
      <p className="text-sm text-zinc-400">{label}</p>
      <p className="mt-3 font-display text-2xl font-semibold text-white">{value}</p>
    </div>
  );
}

export function TournamentPage({
  dashboardMode,
  section,
  session,
  setFlash,
}: {
  dashboardMode: boolean;
  section: TournamentSection;
  session: Session;
  setFlash: (message: FlashMessage) => void;
}) {
  const params = useParams();
  const tournamentKey = params.tournamentKey ?? '';
  const stageItemId = params.stageItemId ? Number(params.stageItemId) : null;
  const isAuthenticated = Boolean(session);
  const isManagementSection =
    !dashboardMode && ['players', 'teams', 'rankings', 'settings', 'stages'].includes(section);
  const isLockedOut = isManagementSection && !isAuthenticated;

  const workspace = useResource(
    () =>
      fetchTournamentBundle(tournamentKey, dashboardMode, isAuthenticated, session?.access_token),
    [dashboardMode, session?.access_token, tournamentKey],
    Boolean(tournamentKey) && !isLockedOut,
  );

  const teamMap = useMemo(
    () => new Map((workspace.data?.teams ?? []).map((team) => [team.id, team] as const)),
    [workspace.data?.teams],
  );
  const stageItemsById = useMemo(() => {
    const map = new Map<number, OpenApi.StageItemWithRounds>();
    workspace.data?.stages.forEach((stage) => {
      stage.stage_items.forEach((item) => map.set(item.id, item));
    });
    return map;
  }, [workspace.data?.stages]);
  const matches = useMemo(
    () => flattenMatches(workspace.data?.stages ?? []).sort(compareMatchesByTime),
    [workspace.data?.stages],
  );

  // Guards must stay below every hook call so the hook order never changes.
  if (isLockedOut) {
    return (
      <ErrorState
        error="This area is only available when logged in."
        title="Read-only mode"
        action={
          <Link
            className="inline-flex rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
            to="/login"
          >
            Log in
          </Link>
        }
      />
    );
  }

  if (workspace.loading) {
    return <LoadingState title="Loading tournament workspace..." />;
  }

  if (workspace.error || !workspace.data) {
    return (
      <ErrorState
        error={workspace.error ?? 'The tournament could not be loaded.'}
        title="Unable to load tournament"
        action={
          <Button onClick={workspace.refresh} type="button">
            Retry
          </Button>
        }
      />
    );
  }

  const tournament = workspace.data.tournament;
  const canManage = workspace.data.canManage;

  if (isManagementSection && !canManage) {
    return (
      <ErrorState
        error="You can view this tournament, but you do not have management access."
        title="Read-only access"
        action={
          <Link
            className="inline-flex rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
            to={`/tournaments/${tournamentKey}`}
          >
            Open overview
          </Link>
        }
      />
    );
  }

  const standings = [...workspace.data.teams].sort((left, right) => {
    if (left.wins !== right.wins) return right.wins - left.wins;
    if (left.draws !== right.draws) return right.draws - left.draws;
    if (left.losses !== right.losses) return left.losses - right.losses;
    return left.name.localeCompare(right.name);
  });
  const stageItemFocus = stageItemId ? (stageItemsById.get(stageItemId) ?? null) : null;

  return (
    <PageShell
      title={tournament.name}
      actions={
        <TournamentNav
          dashboardMode={dashboardMode}
          canManage={canManage}
          tournamentKey={tournamentKey}
        />
      }
    >
      <Surface className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Status" value={TOURNAMENT_STATUS_LABELS[tournament.status]} />
        <MetricCard label="Teams" value={String(workspace.data.teams.length)} />
        <MetricCard
          label="Matches played"
          value={`${matches.filter((entry) => isScored(entry.match)).length} of ${matches.length}`}
        />
      </Surface>

      {section === 'overview' || section === 'dashboard' ? (
        <OverviewSection
          bundle={workspace.data}
          isAuthenticated={canManage}
          matches={matches}
          stageItemsById={stageItemsById}
          tournamentKey={tournamentKey}
        />
      ) : null}
      {section === 'dashboard-bracket' ? (
        <BracketSection bundle={workspace.data} stageItemsById={stageItemsById} teamMap={teamMap} />
      ) : null}
      {section === 'players' ? (
        <PlayersSection bundle={workspace.data} onRefresh={workspace.refresh} setFlash={setFlash} />
      ) : null}
      {section === 'teams' ? (
        <TeamsSection bundle={workspace.data} onRefresh={workspace.refresh} setFlash={setFlash} />
      ) : null}
      {section === 'schedule' || section === 'dashboard-courts' ? (
        <ScheduleSection
          compact={section === 'dashboard-courts'}
          courts={workspace.data.courts}
          isAuthenticated={canManage}
          matches={matches}
          onRefresh={workspace.refresh}
          setFlash={setFlash}
          stageItemsById={stageItemsById}
          tournamentId={tournament.id}
        />
      ) : null}
      {section === 'rankings' ? (
        <RankingsSection
          bundle={workspace.data}
          onRefresh={workspace.refresh}
          setFlash={setFlash}
          standings={standings}
        />
      ) : null}
      {section === 'dashboard-standings' ? (
        <StandingsSection rankings={workspace.data.rankings} standings={standings} />
      ) : null}
      {section === 'dashboard-present-standings' ? (
        <StandingsSection compact rankings={workspace.data.rankings} standings={standings} />
      ) : null}
      {section === 'results' ? (
        <ResultsSection matches={matches} stageItemsById={stageItemsById} />
      ) : null}
      {section === 'settings' ? (
        <SettingsSection
          bundle={workspace.data}
          onRefresh={workspace.refresh}
          setFlash={setFlash}
          tournamentKey={tournamentKey}
        />
      ) : null}
      {section === 'stages' ? (
        <StagesSection
          bundle={workspace.data}
          focusStageItem={stageItemFocus}
          onRefresh={workspace.refresh}
          setFlash={setFlash}
        />
      ) : null}
    </PageShell>
  );
}

export function NotFoundPage() {
  return (
    <PageShell title="Route not found">
      <div className="text-center">
        <Link
          className="inline-flex rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
          to="/"
        >
          Back home
        </Link>
      </div>
    </PageShell>
  );
}
